/**
 * mvu_server.js — 常驻 MVU 引擎，直接执行角色卡脚本（和酒馆助手一样）
 *
 * 用法: node mvu_server.js --card=<卡片文件夹> [--port=8766]
 *
 * 与 run_card_scripts.js 的区别：
 *   - run_card_scripts: 导入时一次性提取 → JSON
 *   - mvu_server:     常驻进程，真实 Zod 验证，实时注入，事件派发
 */

'use strict';

const http = require('http');
const vm = require('vm');
const fs = require('fs');
const path = require('path');
const z = require('zod');
const { extendZod, makeLodash, generateSchemaMeta, generateInitvar, generateScopeMeta, extractInjectionRulesFromScripts } = require('./mvu_shared.js');
const { createSandbox } = require('./tavern_compat.js');
extendZod(z);

// ============================================================
// CLI args
// ============================================================
let cardFolder = null;
let port = 8766;
for (const arg of process.argv) {
  if (arg.startsWith('--card=')) cardFolder = arg.slice(7);
  if (arg.startsWith('--port=')) port = parseInt(arg.slice(7), 10);
}
if (!cardFolder) {
  console.error('用法: node mvu_server.js --card=<卡片文件夹> [--port=8766]');
  process.exit(1);
}

// ============================================================
// lodash 工具
// ============================================================
const _ = makeLodash();

// ============================================================
// 执行卡片脚本，捕获真实 Zod schema 和注入函数
// ============================================================
let capturedSchema = null;
let injectionUpdateFn = null;
let injectionRules = [];
let scriptErrors = [];
let sandboxState = null;
let vmContext = null;

// __LOADCARD_PLACEHOLDER__

function loadCard(cardDir) {
  capturedSchema = null;
  injectionUpdateFn = null;
  injectionRules = [];
  scriptErrors = [];
  sandboxState = null;
  vmContext = null;

  const cardDataPath = path.join(cardDir, '.card_data.json');
  if (!fs.existsSync(cardDataPath)) {
    return { ok: false, error: `.card_data.json 不存在: ${cardDataPath}` };
  }

  let cardData;
  try {
    cardData = JSON.parse(fs.readFileSync(cardDataPath, 'utf-8'));
  } catch (err) {
    return { ok: false, error: `.card_data.json 解析失败: ${err.message}` };
  }
  const tavernHelper = cardData?.data?.extensions?.tavern_helper;
  if (!tavernHelper || !tavernHelper.scripts) {
    return { ok: true, no_scripts: true, message: '卡片无 tavern_helper 脚本' };
  }

  const scripts = tavernHelper.scripts.filter(s => s.enabled !== false);

  // 使用兼容层创建沙箱
  const { sandbox, getState } = createSandbox({ mode: 'runtime', statData: {} });
  sandboxState = getState();
  vmContext = vm.createContext(sandbox);

  function preprocess(content) {
    let out = content;
    out = out.replace(/^import\s+.*?;?\s*$/gm, '// [removed import]');
    out = out.replace(/\.prefault\(/g, '.default(');
    out = out.replace(/\bexport\s+(const|let|var|function|class|async\s+function)\b/g, '$1');
    return out;
  }

  // Classify and execute scripts
  const mvuScripts = [], schemaScripts = [], injectionScripts = [], otherScripts = [];
  for (const script of scripts) {
    if (!script.content || !script.content.trim()) continue;
    const c = script.content;
    const n = script.name || '';
    if (n.includes('Zod') || n.includes('var_update') || c.includes('MagVarUpdate')) {
      mvuScripts.push(script);
    } else if (c.includes('registerMvuSchema')) {
      schemaScripts.push(script);
    } else if (c.includes('injectPrompts')) {
      injectionScripts.push(script);
    } else {
      otherScripts.push(script);
    }
  }

  const ordered = [...mvuScripts, ...schemaScripts, ...injectionScripts, ...otherScripts];

  for (const script of ordered) {
    const name = script.name || 'unknown';
    const processed = preprocess(script.content);
    try {
      const vmScript = new vm.Script(processed, { filename: `${name}.js`, timeout: 10000 });
      vmScript.runInContext(vmContext, { timeout: 10000 });
    } catch (err) {
      scriptErrors.push({ script: name, error: err.message });
    }
  }

  // Execute $(callback) callbacks
  for (const cb of sandboxState.$Callbacks) {
    try { cb(); } catch (err) { /* silent */ }
  }

  // 从兼容层获取捕获的 schema
  capturedSchema = sandboxState.capturedSchema;
  injectionRules = sandboxState.injections;

  // Store injection update function
  if (vmContext.updateKinkInjection) {
    injectionUpdateFn = vmContext.updateKinkInjection;
  }

  // Extract injection rules from keyword script
  if (injectionUpdateFn || injectionScripts.length > 0) {
    injectionRules = extractInjectionRulesFromScripts(scripts);
  }

  return {
    ok: true,
    has_schema: !!capturedSchema,
    has_injection: !!injectionUpdateFn,
    scripts_executed: ordered.length,
    errors: scriptErrors,
  };
}

// ============================================================
// Schema 路径解析与验证
// ============================================================

function unwrapZodType(schema) {
  if (!schema || !schema._def) return schema;
  let s = schema;
  while (s && s._def) {
    const tn = s._def.typeName;
    if (tn === 'ZodDefault' || tn === 'ZodOptional' || tn === 'ZodNullable') {
      s = s._def.innerType;
    } else if (tn === 'ZodEffects') {
      s = s._def.schema;
    } else {
      break;
    }
  }
  return s;
}

function resolveSchemaPath(schema, pathStr) {
  if (!schema || !pathStr) return null;
  const parts = pathStr.split('.');
  let current = unwrapZodType(schema);

  for (const part of parts) {
    if (!current || !current._def) return null;
    const tn = current._def.typeName;

    if (tn === 'ZodObject') {
      const shape = typeof current._def.shape === 'function' ? current._def.shape() : current.shape;
      if (!shape || !(part in shape)) return null;
      current = unwrapZodType(shape[part]);
    } else if (tn === 'ZodRecord') {
      current = unwrapZodType(current._def.valueType);
    } else if (tn === 'ZodArray') {
      current = unwrapZodType(current._def.type);
    } else {
      return null;
    }
  }
  return current;
}

function validateValue(schema, pathStr, value) {
  const field = resolveSchemaPath(schema, pathStr);
  if (!field) return { ok: false, error: `path not found: ${pathStr}` };
  const result = field.safeParse(value);
  if (result.success) return { ok: true };
  return { ok: false, error: result.error.issues.map(i => i.message).join('; ') };
}

// ============================================================
// HTTP 请求体读取辅助
// ============================================================
function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on('data', chunk => chunks.push(chunk));
    req.on('end', () => {
      try {
        resolve(JSON.parse(Buffer.concat(chunks).toString('utf-8')));
      } catch (e) { reject(e); }
    });
    req.on('error', reject);
  });
}

// ============================================================
// HTTP Server
// ============================================================
const server = http.createServer(async (req, res) => {
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    res.writeHead(200);
    res.end('{}');
    return;
  }

  try {
    // --- GET /status ---
    if (req.method === 'GET' && req.url === '/status') {
      res.writeHead(200);
      res.end(JSON.stringify({
        loaded: !!capturedSchema,
        has_injection: !!injectionUpdateFn,
        errors: scriptErrors,
      }));
      return;
    }

    // --- POST /reload ---
    if (req.method === 'POST' && req.url === '/reload') {
      const result = loadCard(cardFolder);
      res.writeHead(result.ok ? 200 : 400);
      res.end(JSON.stringify(result));
      return;
    }

    // --- POST /validate ---
    if (req.method === 'POST' && req.url === '/validate') {
      const { path: p, value } = await readBody(req);
      const field = resolveSchemaPath(capturedSchema, p);
      const result = field
        ? field.safeParse(value)
        : { success: false, error: { issues: [{ message: `path not found: ${p}` }] } };
      const out = result.success
        ? { ok: true }
        : { ok: false, error: result.error.issues.map(i => i.message).join('; ') };
      res.writeHead(200);
      res.end(JSON.stringify(out));
      return;
    }

    // --- POST /validate_all ---
    if (req.method === 'POST' && req.url === '/validate_all') {
      const { commands } = await readBody(req);
      const results = [];
      for (const cmd of (commands || [])) {
        const r = validateValue(capturedSchema, cmd.path, cmd.value);
        results.push({ ...cmd, ...r });
      }
      res.writeHead(200);
      res.end(JSON.stringify({ results }));
      return;
    }

    // --- POST /initvar ---
    if (req.method === 'POST' && req.url === '/initvar') {
      const initvar = generateInitvar(capturedSchema);
      const scope = generateScopeMeta(initvar);
      const schemaMeta = generateSchemaMeta(capturedSchema);
      res.writeHead(200);
      res.end(JSON.stringify({ initvar, scope, schema: schemaMeta }));
      return;
    }

    // --- POST /inject ---
    if (req.method === 'POST' && req.url === '/inject') {
      const { stat_data } = await readBody(req);
      let keywords = [];

      if (injectionRules.length > 0) {
        const rule = injectionRules[0];
        const sourceVal = _.get(stat_data, rule.source_path);
        if (sourceVal && typeof sourceVal === 'string' && sourceVal.trim()) {
          let splitRe = rule.split_pattern;
          if (splitRe.startsWith('/') && splitRe.lastIndexOf('/') > 0) {
            splitRe = splitRe.slice(1, splitRe.lastIndexOf('/'));
          }
          let parts = [];
          try {
            parts = sourceVal.split(new RegExp(splitRe));
          } catch (e) {
            parts = sourceVal.replace(/、/g, ',').replace(/，/g, ',').split(',');
          }
          keywords = parts.map(k => k.trim()).filter(k => k.length > 0)
            .map(k => (rule.prefix && !k.startsWith(rule.prefix)) ? rule.prefix + k : k);
        }
      }

      res.writeHead(200);
      res.end(JSON.stringify({ keywords }));
      return;
    }

    // --- POST /schema ---
    if (req.method === 'POST' && req.url === '/schema') {
      const schemaMeta = generateSchemaMeta(capturedSchema);
      const initvar = generateInitvar(capturedSchema);
      const scope = generateScopeMeta(initvar);
      res.writeHead(200);
      res.end(JSON.stringify({ ...schemaMeta, scope, initvar }));
      return;
    }

    // --- POST /dispatch — 事件派发（供 Python mvu_engine 调用） ---
    if (req.method === 'POST' && req.url === '/dispatch') {
      const { event, args } = await readBody(req);
      if (!sandboxState || !sandboxState.eventBus) {
        res.writeHead(200);
        res.end(JSON.stringify({ ok: true, modified_data: null }));
        return;
      }

      const eventBus = sandboxState.eventBus;
      const listeners = eventBus.listeners[event];
      if (!listeners || listeners.length === 0) {
        res.writeHead(200);
        res.end(JSON.stringify({ ok: true, modified_data: null }));
        return;
      }

      // 执行所有处理器，传入 args
      let modifiedData = null;
      try {
        for (const handler of listeners.slice()) {
          await handler(...(args || []));
        }
        // 如果 args[0] 是 mvu_data 对象，处理器可能已就地修改
        if (args && args.length > 0 && args[0] && typeof args[0] === 'object') {
          modifiedData = args[0];
        }
      } catch (e) {
        res.writeHead(200);
        res.end(JSON.stringify({ ok: false, error: e.message, modified_data: modifiedData }));
        return;
      }

      res.writeHead(200);
      res.end(JSON.stringify({ ok: true, modified_data: modifiedData }));
      return;
    }

    // --- 404 ---
    res.writeHead(404);
    res.end(JSON.stringify({ error: 'not found' }));
  } catch (e) {
    res.writeHead(400);
    res.end(JSON.stringify({ ok: false, error: e.message }));
  }
});

// ============================================================
// 启动
// ============================================================
const loadResult = loadCard(cardFolder);
if (!loadResult.ok) {
  console.error(`[mvu_server] 加载失败: ${loadResult.error}`);
} else if (loadResult.no_scripts) {
  console.log(`[mvu_server] ${loadResult.message}，在 :${port} 以空引擎运行`);
} else {
  console.log(`[mvu_server] Schema=${!!capturedSchema} Injection=${!!injectionUpdateFn} Scripts=${loadResult.scripts_executed} Errors=${scriptErrors.length}`);
}

server.listen(port, '127.0.0.1', () => {
  console.log(`[mvu_server] 监听 http://127.0.0.1:${port}`);
});

process.on('SIGTERM', () => { server.close(); process.exit(0); });
process.on('SIGINT', () => { server.close(); process.exit(0); });

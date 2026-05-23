/**
 * tavern_compat.js — JS-Slash-Runner (酒馆助手) 兼容层
 *
 * 为 AIRP-Pi 的 VM 沙箱提供完整的 TavernHelper API 表面，
 * 使依赖 JS-Slash-Runner 的角色卡脚本能正常执行。
 *
 * 用法:
 *   const { createSandbox } = require('./tavern_compat.js');
 *   const { sandbox, getState } = createSandbox({ mode: 'extract', statData: {} });
 */

'use strict';

const z = require('zod');
const { extendZod, makeLodash } = require('./mvu_shared.js');
extendZod(z);

let _;
try {
  _ = require('lodash');
} catch (e) {
  _ = makeLodash();
}

// ============================================================
// 事件常量
// ============================================================
const tavern_events = {
  APP_READY: 'app_ready',
  EXTRAS_CONNECTED: 'extras_connected',
  MESSAGE_SWIPED: 'message_swiped',
  MESSAGE_SENT: 'message_sent',
  MESSAGE_RECEIVED: 'message_received',
  MESSAGE_EDITED: 'message_edited',
  MESSAGE_DELETED: 'message_deleted',
  MESSAGE_UPDATED: 'message_updated',
  MESSAGE_FILE_EMBEDDED: 'message_file_embedded',
  MESSAGE_REASONING_EDITED: 'message_reasoning_edited',
  MESSAGE_REASONING_DELETED: 'message_reasoning_deleted',
  MESSAGE_SWIPE_DELETED: 'message_swipe_deleted',
  MORE_MESSAGES_LOADED: 'more_messages_loaded',
  IMPERSONATE_READY: 'impersonate_ready',
  CHAT_CHANGED: 'chat_id_changed',
  GENERATION_AFTER_COMMANDS: 'GENERATION_AFTER_COMMANDS',
  GENERATION_STARTED: 'generation_started',
  GENERATION_STOPPED: 'generation_stopped',
  GENERATION_ENDED: 'generation_ended',
  SD_PROMPT_PROCESSING: 'sd_prompt_processing',
  EXTENSIONS_FIRST_LOAD: 'extensions_first_load',
  EXTENSION_SETTINGS_LOADED: 'extension_settings_loaded',
  SETTINGS_LOADED: 'settings_loaded',
  SETTINGS_UPDATED: 'settings_updated',
  MOVABLE_PANELS_RESET: 'movable_panels_reset',
  SETTINGS_LOADED_BEFORE: 'settings_loaded_before',
  SETTINGS_LOADED_AFTER: 'settings_loaded_after',
  CHATCOMPLETION_SOURCE_CHANGED: 'chatcompletion_source_changed',
  CHATCOMPLETION_MODEL_CHANGED: 'chatcompletion_model_changed',
  OAI_PRESET_CHANGED_BEFORE: 'oai_preset_changed_before',
  OAI_PRESET_CHANGED_AFTER: 'oai_preset_changed_after',
  OAI_PRESET_EXPORT_READY: 'oai_preset_export_ready',
  OAI_PRESET_IMPORT_READY: 'oai_preset_import_ready',
  WORLDINFO_SETTINGS_UPDATED: 'worldinfo_settings_updated',
  WORLDINFO_UPDATED: 'worldinfo_updated',
  CHARACTER_EDITOR_OPENED: 'character_editor_opened',
  CHARACTER_EDITED: 'character_edited',
  CHARACTER_PAGE_LOADED: 'character_page_loaded',
  USER_MESSAGE_RENDERED: 'user_message_rendered',
  CHARACTER_MESSAGE_RENDERED: 'character_message_rendered',
  FORCE_SET_BACKGROUND: 'force_set_background',
  CHAT_DELETED: 'chat_deleted',
  CHAT_CREATED: 'chat_created',
  GENERATE_BEFORE_COMBINE_PROMPTS: 'generate_before_combine_prompts',
  GENERATE_AFTER_COMBINE_PROMPTS: 'generate_after_combine_prompts',
  GENERATE_AFTER_DATA: 'generate_after_data',
  WORLD_INFO_ACTIVATED: 'world_info_activated',
  TEXT_COMPLETION_SETTINGS_READY: 'text_completion_settings_ready',
  CHAT_COMPLETION_SETTINGS_READY: 'chat_completion_settings_ready',
  CHAT_COMPLETION_PROMPT_READY: 'chat_completion_prompt_ready',
  CHARACTER_FIRST_MESSAGE_SELECTED: 'character_first_message_selected',
  CHARACTER_DELETED: 'characterDeleted',
  CHARACTER_DUPLICATED: 'character_duplicated',
  CHARACTER_RENAMED: 'character_renamed',
  CHARACTER_RENAMED_IN_PAST_CHAT: 'character_renamed_in_past_chat',
  SMOOTH_STREAM_TOKEN_RECEIVED: 'stream_token_received',
  STREAM_TOKEN_RECEIVED: 'stream_token_received',
  STREAM_REASONING_DONE: 'stream_reasoning_done',
  FILE_ATTACHMENT_DELETED: 'file_attachment_deleted',
  WORLDINFO_FORCE_ACTIVATE: 'worldinfo_force_activate',
  OPEN_CHARACTER_LIBRARY: 'open_character_library',
  ONLINE_STATUS_CHANGED: 'online_status_changed',
  IMAGE_SWIPED: 'image_swiped',
  CONNECTION_PROFILE_LOADED: 'connection_profile_loaded',
  CONNECTION_PROFILE_CREATED: 'connection_profile_created',
  CONNECTION_PROFILE_DELETED: 'connection_profile_deleted',
  CONNECTION_PROFILE_UPDATED: 'connection_profile_updated',
  TOOL_CALLS_PERFORMED: 'tool_calls_performed',
  TOOL_CALLS_RENDERED: 'tool_calls_rendered',
  CHARACTER_MANAGEMENT_DROPDOWN: 'charManagementDropdown',
  SECRET_WRITTEN: 'secret_written',
  SECRET_DELETED: 'secret_deleted',
  SECRET_ROTATED: 'secret_rotated',
  SECRET_EDITED: 'secret_edited',
  PRESET_CHANGED: 'preset_changed',
  PRESET_DELETED: 'preset_deleted',
  PRESET_RENAMED: 'preset_renamed',
  PRESET_RENAMED_BEFORE: 'preset_renamed_before',
  MAIN_API_CHANGED: 'main_api_changed',
  WORLDINFO_ENTRIES_LOADED: 'worldinfo_entries_loaded',
  WORLDINFO_SCAN_DONE: 'worldinfo_scan_done',
  MEDIA_ATTACHMENT_DELETED: 'media_attachment_deleted',
};

const iframe_events = {
  MESSAGE_IFRAME_RENDER_STARTED: 'message_iframe_render_started',
  MESSAGE_IFRAME_RENDER_ENDED: 'message_iframe_render_ended',
  GENERATION_STARTED: 'js_generation_started',
  STREAM_TOKEN_RECEIVED_FULLY: 'js_stream_token_received_fully',
  STREAM_TOKEN_RECEIVED_INCREMENTALLY: 'js_stream_token_received_incrementally',
  GENERATION_ENDED: 'js_generation_ended',
};

// ============================================================
// 事件总线
// ============================================================
function createEventBus() {
  const listeners = {};

  function getList(event) {
    if (!listeners[event]) listeners[event] = [];
    return listeners[event];
  }

  function eventOn(event_type, listener) {
    const list = getList(event_type);
    if (!list.includes(listener)) {
      list.push(listener);
    }
    return { stop: () => eventRemoveListener(event_type, listener) };
  }

  function eventOnce(event_type, listener) {
    const wrapper = async (...args) => {
      eventRemoveListener(event_type, wrapper);
      return listener(...args);
    };
    wrapper._original = listener;
    return eventOn(event_type, wrapper);
  }

  function eventMakeFirst(event_type, listener) {
    const list = getList(event_type);
    const idx = list.indexOf(listener);
    if (idx > 0) list.splice(idx, 1);
    if (!list.includes(listener)) list.unshift(listener);
    return { stop: () => eventRemoveListener(event_type, listener) };
  }

  function eventMakeLast(event_type, listener) {
    const list = getList(event_type);
    const idx = list.indexOf(listener);
    if (idx >= 0) list.splice(idx, 1);
    list.push(listener);
    return { stop: () => eventRemoveListener(event_type, listener) };
  }

  async function eventEmit(event_type, ...data) {
    const list = getList(event_type).slice();
    for (const fn of list) {
      try { await fn(...data); } catch (e) { /* silent */ }
    }
  }

  function eventEmitAndWait(event_type, ...data) {
    const list = getList(event_type).slice();
    for (const fn of list) {
      try { fn(...data); } catch (e) { /* silent */ }
    }
  }

  function eventRemoveListener(event_type, listener) {
    const list = getList(event_type);
    const idx = list.indexOf(listener);
    if (idx >= 0) list.splice(idx, 1);
  }

  function eventClearEvent(event_type) {
    listeners[event_type] = [];
  }

  function eventClearListener(listener) {
    for (const event of Object.keys(listeners)) {
      const list = listeners[event];
      const idx = list.indexOf(listener);
      if (idx >= 0) list.splice(idx, 1);
    }
  }

  function eventClearAll() {
    for (const key of Object.keys(listeners)) {
      delete listeners[key];
    }
  }

  return {
    listeners,
    eventOn,
    eventOnce,
    eventMakeFirst,
    eventMakeLast,
    eventEmit,
    eventEmitAndWait,
    eventRemoveListener,
    eventClearEvent,
    eventClearListener,
    eventClearAll,
  };
}

// ============================================================
// createSandbox — 工厂函数
// ============================================================

/**
 * @param {Object} options
 * @param {'extract'|'runtime'} options.mode - extract=导入时提取, runtime=运行时验证
 * @param {Object} options.statData - 变量数据引用（runtime 模式下为活跃对象）
 * @returns {{ sandbox: Object, getState: Function }}
 */
function createSandbox(options = {}) {
  const { mode = 'extract', statData = {} } = options;

  // --- 状态 ---
  const capturedSchemas = [];
  const injections = [];
  const $Callbacks = [];
  const globals = {};
  const globalWaiters = {};
  const scriptStores = {};

  // --- 事件总线 ---
  const eventBus = createEventBus();

  // --- registerMvuSchema ---
  function registerMvuSchema(schema) {
    capturedSchemas.push(schema);
  }

  // --- injectPrompts ---
  function injectPrompts(prompts, opts) {
    const ids = [];
    for (const p of prompts || []) {
      const id = p.id || `inj_${injections.length}`;
      ids.push(id);
      injections.push({
        id,
        position: p.position || 'none',
        depth: typeof p.depth === 'number' ? p.depth : 0,
        role: p.role || 'system',
        content: p.content || '',
        should_scan: !!p.should_scan,
        once: opts?.once || false,
      });
    }
    return {
      uninject: () => {
        for (const id of ids) {
          const idx = injections.findIndex(inj => inj.id === id);
          if (idx >= 0) injections.splice(idx, 1);
        }
      },
    };
  }

  function uninjectPrompts(ids) {
    for (const id of (ids || [])) {
      const idx = injections.findIndex(inj => inj.id === id);
      if (idx >= 0) injections.splice(idx, 1);
    }
  }

  // --- Mvu 命名空间 ---
  const Mvu = {
    events: {
      VARIABLE_INITIALIZED: 'mag_variable_initiailized',
      VARIABLE_UPDATE_STARTED: 'mag_variable_update_started',
      COMMAND_PARSED: 'mag_command_parsed',
      VARIABLE_UPDATE_ENDED: 'mag_variable_update_ended',
      BEFORE_MESSAGE_UPDATE: 'mag_before_message_update',
    },
    getMvuData: function (opts) {
      return { stat_data: statData, initialized_lorebooks: {} };
    },
    replaceMvuData: async function (mvu_data, opts) {
      if (mvu_data && mvu_data.stat_data) {
        Object.keys(statData).forEach(k => delete statData[k]);
        Object.assign(statData, mvu_data.stat_data);
      }
    },
    parseMessage: async function (message, old_data) {
      return old_data || { stat_data: statData, initialized_lorebooks: {} };
    },
    isDuringExtraAnalysis: function () { return false; },
  };

  // --- 全局共享 ---
  function initializeGlobal(name, value) {
    globals[name] = value;
    if (globalWaiters[name]) {
      for (const resolve of globalWaiters[name]) resolve(value);
      delete globalWaiters[name];
    }
  }

  function waitGlobalInitialized(name) {
    if (name in globals) return Promise.resolve(globals[name]);
    return new Promise(resolve => {
      if (!globalWaiters[name]) globalWaiters[name] = [];
      globalWaiters[name].push(resolve);
    });
  }

  // --- 变量操作 ---
  function getStatDataRef() { return statData; }

  function getVariables(option) {
    const type = option?.type || 'chat';
    switch (type) {
      case 'chat': case 'message': case 'character': case 'global':
        return _.cloneDeep(statData);
      case 'script':
        return _.cloneDeep(scriptStores[option?.script_id] || {});
      default:
        return {};
    }
  }

  function replaceVariables(variables, option) {
    const type = option?.type || 'chat';
    switch (type) {
      case 'chat': case 'message': case 'character': case 'global':
        Object.keys(statData).forEach(k => delete statData[k]);
        Object.assign(statData, variables);
        break;
      case 'script':
        scriptStores[option?.script_id || '_default'] = variables;
        break;
    }
  }

  function updateVariablesWith(updater, option) {
    const vars = getVariables(option);
    const result = updater(vars);
    const updated = result !== undefined ? result : vars;
    replaceVariables(updated, option);
    return updated;
  }

  function insertOrAssignVariables(variables, option) {
    const current = getVariables(option);
    const merged = _.merge ? _.merge({}, current, variables) : Object.assign({}, current, variables);
    replaceVariables(merged, option);
    return merged;
  }

  function insertVariables(variables, option) {
    const current = getVariables(option);
    for (const [key, val] of Object.entries(variables || {})) {
      if (!(key in current)) current[key] = val;
    }
    replaceVariables(current, option);
    return current;
  }

  function deleteVariable(variable_path, option) {
    const vars = getVariables(option);
    const pathParts = variable_path.split('.');
    let obj = vars;
    for (let i = 0; i < pathParts.length - 1; i++) {
      if (obj == null || typeof obj !== 'object') return { variables: vars, delete_occurred: false };
      obj = obj[pathParts[i]];
    }
    const lastKey = pathParts[pathParts.length - 1];
    const existed = obj != null && typeof obj === 'object' && lastKey in obj;
    if (existed) delete obj[lastKey];
    replaceVariables(vars, option);
    return { variables: vars, delete_occurred: existed };
  }

  function getAllVariables() {
    return _.cloneDeep(statData);
  }

  function registerVariableSchema(schema, option) {
    // UI-only in SillyTavern; no-op in headless mode
  }

  // --- jQuery mock ---
  function $(fn) {
    if (typeof fn === 'function') $Callbacks.push(fn);
  }

  // --- No-op stubs for UI features ---
  const noop = () => {};
  const noopAsync = async () => {};
  const noopArr = () => [];
  const noopObj = () => ({});
  const noopStr = () => '';
  const noopBool = () => false;
  const noopThrow = (msg) => () => { throw new Error(msg); };

  const TavernHelper = {
    // Audio
    playAudio: noop, pauseAudio: noop, getAudioList: noopArr,
    replaceAudioList: noop, appendAudioList: noop,
    getAudioSettings: noopObj, setAudioSettings: noop,
    audioEnable: noop, audioImport: noop, audioMode: noop,
    audioPlay: noop, audioSelect: noop,
    // Character
    getCharacterNames: noopArr, getCurrentCharacterName: noopStr,
    createCharacter: noopAsync, createOrReplaceCharacter: noopAsync,
    deleteCharacter: noopAsync, getCharacter: noopObj,
    replaceCharacter: noopAsync, updateCharacterWith: noopAsync,
    // Chat Messages
    getChatMessages: noopArr, setChatMessages: noop,
    setChatMessage: noop, createChatMessages: noop,
    deleteChatMessages: noop, rotateChatMessages: noop,
    // Displayed Message
    formatAsDisplayedMessage: noopStr, retrieveDisplayedMessage: noopStr,
    refreshOneMessage: noop,
    // Extension
    isAdmin: noopBool, getTavernHelperExtensionId: noopStr,
    getExtensionType: noopStr, getExtensionStatus: noopObj,
    isInstalledExtension: noopBool, installExtension: noopAsync,
    uninstallExtension: noopAsync, reinstallExtension: noopAsync,
    updateExtension: noopAsync,
    // Generate
    generate: noopThrow('AI generation not available in headless mode'),
    generateRaw: noopThrow('AI generation not available in headless mode'),
    getModelList: noopArr, getProxyPresetNames: noopArr,
    stopGenerationById: noop, stopAllGeneration: noop,
    // Global
    initializeGlobal, waitGlobalInitialized,
    // Inject
    injectPrompts, uninjectPrompts,
    // Lorebook
    getLorebookSettings: noopObj, setLorebookSettings: noop,
    getCharLorebooks: noopArr, setCurrentCharLorebooks: noop,
    getLorebooks: noopArr, deleteLorebook: noopAsync,
    createLorebook: noopAsync, getCurrentCharPrimaryLorebook: noopObj,
    getChatLorebook: noopObj, setChatLorebook: noop,
    getOrCreateChatLorebook: noopObj,
    // Lorebook Entry
    getLorebookEntries: noopArr, replaceLorebookEntries: noop,
    updateLorebookEntriesWith: noop, setLorebookEntries: noop,
    createLorebookEntries: noop, createLorebookEntry: noop,
    deleteLorebookEntries: noop, deleteLorebookEntry: noop,
    // Macro
    registerMacroLike: noop, unregisterMacroLike: noop,
    substitudeMacros: (str) => str || '',
    // Preset
    getPresetNames: noopArr, getLoadedPresetName: noopStr,
    loadPreset: noopAsync, createPreset: noopAsync,
    createOrReplacePreset: noopAsync, deletePreset: noopAsync,
    renamePreset: noopAsync, getPreset: noopObj,
    replacePreset: noopAsync, updatePresetWith: noopAsync,
    setPreset: noop, isPresetNormalPrompt: noopBool,
    isPresetSystemPrompt: noopBool, isPresetPlaceholderPrompt: noopBool,
    // Raw Character
    getCharData: noopObj, getCharAvatarPath: noopStr,
    getChatHistoryBrief: noopArr, getChatHistoryDetail: noopArr,
    // Script
    getAllEnabledScriptButtons: noopArr, getScriptTrees: noopArr,
    replaceScriptTrees: noop, updateScriptTreesWith: noop,
    // Slash
    triggerSlash: noopAsync, triggerSlashWithResult: noopAsync,
    // Tavern Regex
    formatAsTavernRegexedString: (str) => str || '',
    isCharacterTavernRegexesEnabled: noopBool,
    getTavernRegexes: noopArr, replaceTavernRegexes: noop,
    updateTavernRegexesWith: noop,
    // Util
    substitudeMacros: (str) => str || '',
    getLastMessageId: () => -1, errorCatched: noop, getMessageId: () => -1,
    // Variables
    getVariables, replaceVariables, updateVariablesWith,
    insertOrAssignVariables, insertVariables, deleteVariable,
    getAllVariables, registerVariableSchema,
    // Version
    getTavernHelperVersion: () => '4.8.7',
    getFrontendVersion: noopStr, updateTavernHelper: noopAsync,
    updateFrontendVersion: noopAsync, getTavernVersion: noopStr,
    // Worldbook
    getWorldbookNames: noopArr, getGlobalWorldbookNames: noopArr,
    rebindGlobalWorldbooks: noop, getCharWorldbookNames: noopArr,
    rebindCharWorldbooks: noop, getChatWorldbookName: noopStr,
    rebindChatWorldbook: noop, getOrCreateChatWorldbook: noopObj,
    createWorldbook: noopAsync, createOrReplaceWorldbook: noopAsync,
    deleteWorldbook: noopAsync, getWorldbook: noopObj,
    replaceWorldbook: noopAsync, updateWorldbookWith: noopAsync,
    createWorldbookEntries: noop, deleteWorldbookEntries: noop,
    // Import Raw
    importRawCharacter: noopAsync, importRawPreset: noopAsync,
    importRawChat: noopAsync, importRawWorldbook: noopAsync,
    importRawTavernRegex: noopAsync,
  };

  // --- 组装沙箱 ---
  const sandbox = {
    z,
    _,
    registerMvuSchema,
    injectPrompts,
    uninjectPrompts,
    eventOn: eventBus.eventOn,
    eventOnce: eventBus.eventOnce,
    eventMakeFirst: eventBus.eventMakeFirst,
    eventMakeLast: eventBus.eventMakeLast,
    eventEmit: eventBus.eventEmit,
    eventEmitAndWait: eventBus.eventEmitAndWait,
    eventRemoveListener: eventBus.eventRemoveListener,
    eventClearEvent: eventBus.eventClearEvent,
    eventClearListener: eventBus.eventClearListener,
    eventClearAll: eventBus.eventClearAll,
    Mvu,
    initializeGlobal,
    waitGlobalInitialized,
    getVariables,
    replaceVariables,
    updateVariablesWith,
    insertOrAssignVariables,
    insertVariables,
    deleteVariable,
    getAllVariables,
    registerVariableSchema,
    $,
    tavern_events,
    iframe_events,
    TavernHelper,
    console: { log: noop, error: noop, warn: noop, info: noop, debug: noop },
    setTimeout,
    clearTimeout,
    setInterval: noop,
    clearInterval: noop,
    Promise, JSON, Object, Array, String, Number, Boolean,
    Math, Date, RegExp, Error, Map, Set, WeakMap, WeakSet,
    parseInt, parseFloat, isNaN, isFinite,
    undefined, NaN, Infinity,
    Symbol,
    Proxy,
    Reflect,
    encodeURIComponent, decodeURIComponent,
    encodeURI, decodeURI,
    atob: typeof atob !== 'undefined' ? atob : noop,
    btoa: typeof btoa !== 'undefined' ? btoa : noop,
  };

  // --- 获取内部状态（供宿主代码使用） ---
  function getState() {
    return {
      capturedSchemas,
      capturedSchema: capturedSchemas[capturedSchemas.length - 1] || null,
      injections,
      $Callbacks,
      eventBus,
      globals,
    };
  }

  return { sandbox, getState };
}

module.exports = { createSandbox, tavern_events, iframe_events, createEventBus };

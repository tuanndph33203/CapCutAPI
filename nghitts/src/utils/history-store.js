/**
 * IndexedDB-backed store for TTS generation history.
 * One object store "entries" with keyPath "id".
 */

const DB_NAME = 'piper-tts-history';
const STORE_NAME = 'entries';
const MAX_ENTRIES = 50;

function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onerror = () => reject(req.error);
    req.onsuccess = () => resolve(req.result);
    req.onupgradeneeded = (e) => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: 'id' });
      }
    };
  });
}

/**
 * @param {{ text: string, model: string, voice: number|string, speed: number, lang: string, audio: Blob }} entry
 * @returns {Promise<string>} id of the added entry
 */
export async function addEntry({ text, model, voice, speed, lang, audio }) {
  const id = `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  const record = {
    id,
    text,
    model,
    voice,
    speed,
    lang,
    createdAt: Date.now(),
    audio,
  };
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite');
    const store = tx.objectStore(STORE_NAME);
    store.add(record);
    tx.oncomplete = async () => {
      db.close();
      await trimToCap();
      resolve(id);
    };
    tx.onerror = () => {
      db.close();
      reject(tx.error);
    };
  });
}

async function trimToCap() {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite');
    const store = tx.objectStore(STORE_NAME);
    const req = store.getAll();
    req.onsuccess = () => {
      const entries = req.result;
      if (entries.length <= MAX_ENTRIES) {
        db.close();
        resolve();
        return;
      }
      entries.sort((a, b) => a.createdAt - b.createdAt);
      const toDelete = entries.slice(0, entries.length - MAX_ENTRIES);
      toDelete.forEach((e) => store.delete(e.id));
      tx.oncomplete = () => {
        db.close();
        resolve();
      };
    };
    req.onerror = () => {
      db.close();
      reject(req.error);
    };
  });
}

/**
 * @returns {Promise<Array<{ id: string, text: string, model: string, voice: number|string, speed: number, lang: string, createdAt: number, audio: Blob }>>}
 */
export async function getEntries() {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readonly');
    const store = tx.objectStore(STORE_NAME);
    const req = store.getAll();
    req.onsuccess = () => {
      const entries = req.result || [];
      entries.sort((a, b) => (b.createdAt || 0) - (a.createdAt || 0));
      db.close();
      resolve(entries);
    };
    req.onerror = () => {
      db.close();
      reject(req.error);
    };
  });
}

/**
 * @param {string} id
 * @returns {Promise<void>}
 */
export async function deleteEntry(id) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite');
    const store = tx.objectStore(STORE_NAME);
    store.delete(id);
    tx.oncomplete = () => {
      db.close();
      resolve();
    };
    tx.onerror = () => {
      db.close();
      reject(tx.error);
    };
  });
}

/**
 * Clear all history entries.
 * @returns {Promise<void>}
 */
export async function clearAll() {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite');
    const store = tx.objectStore(STORE_NAME);
    store.clear();
    tx.oncomplete = () => {
      db.close();
      resolve();
    };
    tx.onerror = () => {
      db.close();
      reject(tx.error);
    };
  });
}

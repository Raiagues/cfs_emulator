import {readFrames, request} from './api.js';

const subscriptions = new Map();
let source;

export function onUpdate(topics, callback) {
  const entry = Symbol();
  let pending = false, active = false;
  const deliver = async () => {
    pending = true;
    if (active) return;
    active = true;
    try {
      while (pending && subscriptions.has(entry)) {
        pending = false;
        await callback();
      }
    } finally {active = false;}
  };
  subscriptions.set(entry, {topics, callback:deliver});
  if (!source) {
    source = new EventSource('/api/events');
    source.onmessage = event => {
      const changed = JSON.parse(event.data);
      for (const {topics, callback} of subscriptions.values()) {
        if (topics.some(topic => changed.includes(topic))) callback(changed);
      }
    };
  }
  return () => {
    subscriptions.delete(entry);
    if (!subscriptions.size) {source.close(); source = null;}
  };
}

export async function* jobLog(id, cursor, signal) {
  const query = new URLSearchParams({id, cursor});
  const response = await request('jobs/stream?' + query, undefined, {signal});
  yield* readFrames(response);
}

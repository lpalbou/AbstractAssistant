/** A synchronous store around turnReducer, so the follower reads the state
 * it just produced (React's useReducer updates on the next render). */
import { initialTurn, turnReducer, type TurnAction, type TurnState } from "./run_events";

export type TurnStore = {
  getState: () => TurnState;
  dispatch: (a: TurnAction) => void;
  subscribe: (fn: () => void) => () => void;
};

export function createTurnStore(rootRunId: string): TurnStore {
  let state = initialTurn(rootRunId);
  const subs = new Set<() => void>();
  return {
    getState: () => state,
    dispatch: (a) => {
      const next = turnReducer(state, a);
      if (next !== state) {
        state = next;
        subs.forEach((fn) => fn());
      }
    },
    subscribe: (fn) => {
      subs.add(fn);
      return () => subs.delete(fn);
    },
  };
}

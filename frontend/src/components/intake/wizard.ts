/** Pure intake-wizard state machine — exported for unit tests (Chunk 7:
 *  branching yes/no past clients). */

export type IntakeStep = "product" | "past-clients-question" | "past-clients" | "review";

export interface PastClientDraft {
  details: string;
  acquisition_story: string;
}

export interface IntakeState {
  step: IntakeStep;
  product: { name: string; description: string; type: "product" | "skill" };
  hasPastClients: boolean | null;
  clients: PastClientDraft[];
}

export const INITIAL_INTAKE: IntakeState = {
  step: "product",
  product: { name: "", description: "", type: "product" },
  hasPastClients: null,
  clients: [],
};

export function nextStep(state: IntakeState): IntakeState {
  switch (state.step) {
    case "product":
      return { ...state, step: "past-clients-question" };
    case "past-clients-question":
      // THE branch: YES -> per-client forms; NO -> straight to review
      // (Flow 2, the 144-step pipeline, needs no client entry).
      return state.hasPastClients
        ? {
            ...state,
            step: "past-clients",
            clients: state.clients.length
              ? state.clients
              : [{ details: "", acquisition_story: "" }],
          }
        : { ...state, step: "review", clients: [] };
    case "past-clients":
      return { ...state, step: "review" };
    default:
      return state;
  }
}

export function prevStep(state: IntakeState): IntakeState {
  switch (state.step) {
    case "past-clients-question":
      return { ...state, step: "product" };
    case "past-clients":
      return { ...state, step: "past-clients-question" };
    case "review":
      return {
        ...state,
        step: state.hasPastClients ? "past-clients" : "past-clients-question",
      };
    default:
      return state;
  }
}

export function canAdvance(state: IntakeState): boolean {
  switch (state.step) {
    case "product":
      return state.product.name.trim().length > 0 &&
             state.product.description.trim().length > 0;
    case "past-clients-question":
      return state.hasPastClients !== null;
    case "past-clients":
      return (
        state.clients.length > 0 &&
        state.clients.every(
          (c) => c.details.trim() && c.acquisition_story.trim(),
        )
      );
    default:
      return true;
  }
}

/* eslint-disable */
/**
 * GENERATED FILE — do not edit by hand.
 * Source: backend/src/magi/events.py -> schema/magi-events.schema.json
 * Regenerate: (cd backend && uv run magi-schema) && (cd frontend && npm run gen:types)
 */

/**
 * Any event emitted by a MAGI deliberation run.
 */
export type MagiEvent =
  | RunStarted
  | PhaseStarted
  | AgentThinking
  | AgentMessage
  | AgentRevisedPosition
  | VoteCast
  | Verdict
  | RunError
  | RunCompleted;
export type VerdictRule = "majority" | "unanimous";
export type Phase = "opening" | "debate" | "vote" | "verdict";
/**
 * An agent's current leaning on the proposition (pre-vote).
 */
export type Stance = "APPROVE" | "DENY" | "UNDECIDED";
export type VoteChoice = "APPROVE" | "DENY" | "ABSTAIN";
export type Outcome = "APPROVED" | "DENIED" | "DEADLOCK";
export type RunStatus = "completed" | "failed";

export interface RunStarted {
  agents: AgentInfo[];
  config: RunConfig;
  question: string;
  run_id: string;
  schema_version: string;
  /**
   * 1-based, strictly increasing within a run.
   */
  seq: number;
  timestamp: string;
  type: "run_started";
}
export interface AgentInfo {
  /**
   * CSS color used for this agent in the UI.
   */
  color: string;
  /**
   * Stable lowercase id, e.g. 'melchior'.
   */
  id: string;
  /**
   * Display name, e.g. 'MELCHIOR-1'.
   */
  name: string;
  priorities: string[];
  /**
   * Persona title, e.g. 'The Scientist'.
   */
  title: string;
}
export interface RunConfig {
  early_consensus: boolean;
  max_rounds: number;
  mock: boolean;
  model: string;
  verdict_rule: VerdictRule;
}
export interface PhaseStarted {
  phase: Phase;
  /**
   * 0 for opening, 1..N for debate rounds, null otherwise.
   */
  round: number | null;
  run_id: string;
  /**
   * 1-based, strictly increasing within a run.
   */
  seq: number;
  timestamp: string;
  type: "phase_started";
}
export interface AgentThinking {
  agent_id: string;
  phase: Phase;
  round: number | null;
  run_id: string;
  /**
   * 1-based, strictly increasing within a run.
   */
  seq: number;
  timestamp: string;
  type: "agent_thinking";
}
export interface AgentMessage {
  agent_id: string;
  content: string;
  message_id: string;
  phase: Phase;
  reply_to: ReplyRef[];
  round: number;
  run_id: string;
  /**
   * 1-based, strictly increasing within a run.
   */
  seq: number;
  stance: Stance;
  /**
   * One-sentence statement of the agent's current position.
   */
  summary: string;
  timestamp: string;
  type: "agent_message";
}
export interface ReplyRef {
  agent_id: string;
  message_id: string;
}
export interface AgentRevisedPosition {
  agent_id: string;
  message_id: string;
  new_stance: Stance;
  new_summary: string;
  previous_stance: Stance;
  previous_summary: string;
  reason: string;
  round: number;
  run_id: string;
  /**
   * 1-based, strictly increasing within a run.
   */
  seq: number;
  timestamp: string;
  type: "agent_revised_position";
}
export interface VoteCast {
  agent_id: string;
  confidence: number;
  rationale: string;
  run_id: string;
  /**
   * 1-based, strictly increasing within a run.
   */
  seq: number;
  timestamp: string;
  type: "vote_cast";
  vote: VoteChoice;
}
export interface Verdict {
  /**
   * Mean confidence of the agents on the winning side.
   */
  confidence: number;
  decisive_arguments: DecisiveArgument[];
  outcome: Outcome;
  rule: VerdictRule;
  run_id: string;
  /**
   * 1-based, strictly increasing within a run.
   */
  seq: number;
  summary: string;
  tally: Tally;
  timestamp: string;
  type: "verdict";
}
export interface DecisiveArgument {
  agent_id: string;
  message_id: string | null;
  reason: string;
}
export interface Tally {
  abstain: number;
  approve: number;
  deny: number;
}
export interface RunError {
  agent_id: string | null;
  fatal: boolean;
  message: string;
  run_id: string;
  /**
   * 1-based, strictly increasing within a run.
   */
  seq: number;
  timestamp: string;
  type: "run_error";
}
export interface RunCompleted {
  duration_ms: number;
  run_id: string;
  /**
   * 1-based, strictly increasing within a run.
   */
  seq: number;
  status: RunStatus;
  timestamp: string;
  type: "run_completed";
}

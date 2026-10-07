/** DOM id of a transcript message, used for citation links. */
export function entryAnchor(messageId: string): string {
  return `msg-${messageId}`
}

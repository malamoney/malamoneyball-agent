import type { ConversationSummary } from "./api";

type SidebarProps = {
  conversations: ConversationSummary[];
  openId: string | null;
  /** While an Answer streams, switching Conversations is blocked. */
  busy: boolean;
  onOpen: (conversationId: string) => void;
  onNew: () => void;
};

/** The User's Conversations, most recently used first, with the open one marked. */
export function Sidebar({ conversations, openId, busy, onOpen, onNew }: SidebarProps) {
  return (
    <nav
      aria-label="Conversations"
      className="flex w-64 shrink-0 flex-col border-r border-stone-200 bg-white"
    >
      <div className="p-3">
        <button
          type="button"
          onClick={onNew}
          disabled={busy}
          className="w-full rounded-md border border-stone-300 px-3 py-2 text-left text-sm font-medium hover:bg-stone-100 disabled:cursor-not-allowed disabled:opacity-50"
        >
          New Conversation
        </button>
      </div>
      <ul className="flex-1 space-y-0.5 overflow-y-auto px-2 pb-3">
        {conversations.map((conversation) => {
          const isOpen = conversation.id === openId;
          return (
            <li key={conversation.id}>
              <button
                type="button"
                onClick={() => onOpen(conversation.id)}
                disabled={busy}
                aria-current={isOpen ? "page" : undefined}
                title={conversation.title}
                className={`w-full rounded-md px-3 py-2 text-left text-sm disabled:cursor-not-allowed ${
                  isOpen
                    ? "bg-emerald-50 font-medium text-emerald-900"
                    : "text-stone-700 hover:bg-stone-100"
                }`}
              >
                <span className="block truncate">{conversation.title}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

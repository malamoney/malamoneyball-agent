import { type FormEvent, type KeyboardEvent, useRef, useState } from "react";

import type { ConversationSummary } from "./api";

type SidebarProps = {
  conversations: ConversationSummary[];
  openId: string | null;
  /** While an Answer streams, switching or changing Conversations is blocked. */
  busy: boolean;
  onOpen: (conversationId: string) => void;
  onNew: () => void;
  onRename: (conversationId: string, title: string) => void;
  onDelete: (conversationId: string) => void;
};

/** The User's Conversations, most recently used first, with the open one marked. */
export function Sidebar({
  conversations,
  openId,
  busy,
  onOpen,
  onNew,
  onRename,
  onDelete,
}: SidebarProps) {
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<ConversationSummary | null>(null);

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
          if (conversation.id === renamingId) {
            return (
              <li key={conversation.id}>
                <RenameForm
                  title={conversation.title}
                  onDone={(title) => {
                    setRenamingId(null);
                    if (title && title !== conversation.title) onRename(conversation.id, title);
                  }}
                />
              </li>
            );
          }
          return (
            <li
              key={conversation.id}
              className={`group flex items-center rounded-md ${
                isOpen ? "bg-emerald-50 text-emerald-900" : "text-stone-700 hover:bg-stone-100"
              }`}
            >
              <button
                type="button"
                onClick={() => onOpen(conversation.id)}
                disabled={busy}
                aria-current={isOpen ? "page" : undefined}
                title={conversation.title}
                className={`min-w-0 flex-1 px-3 py-2 text-left text-sm disabled:cursor-not-allowed ${
                  isOpen ? "font-medium" : ""
                }`}
              >
                <span className="block truncate">{conversation.title}</span>
              </button>
              {/* Always shown for the open Conversation, on hover or focus for others. */}
              <span
                className={`flex shrink-0 pr-1 ${
                  isOpen ? "" : "opacity-0 group-focus-within:opacity-100 group-hover:opacity-100"
                }`}
              >
                <IconButton
                  label={`Rename "${conversation.title}"`}
                  disabled={busy}
                  onClick={() => setRenamingId(conversation.id)}
                >
                  ✎
                </IconButton>
                <IconButton
                  label={`Delete "${conversation.title}"`}
                  disabled={busy}
                  onClick={() => setDeleting(conversation)}
                >
                  ×
                </IconButton>
              </span>
            </li>
          );
        })}
      </ul>
      {deleting && (
        <ConfirmDelete
          title={deleting.title}
          onCancel={() => setDeleting(null)}
          onConfirm={() => {
            setDeleting(null);
            onDelete(deleting.id);
          }}
        />
      )}
    </nav>
  );
}

function IconButton({
  label,
  disabled,
  onClick,
  children,
}: {
  label: string;
  disabled: boolean;
  onClick: () => void;
  children: string;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className="rounded px-1.5 py-1 text-sm text-stone-500 hover:bg-stone-200 hover:text-stone-900 disabled:cursor-not-allowed disabled:opacity-50"
    >
      <span aria-hidden="true">{children}</span>
    </button>
  );
}

/** An inline title editor: Enter or leaving the field saves, Escape cancels. */
function RenameForm({ title, onDone }: { title: string; onDone: (title: string | null) => void }) {
  const [draft, setDraft] = useState(title);
  // Enter or Escape closes the field, which can also blur it; finish only once.
  const finished = useRef(false);

  function finish(result: string | null) {
    if (finished.current) return;
    finished.current = true;
    onDone(result);
  }

  function save(event?: FormEvent) {
    event?.preventDefault();
    finish(draft.trim() || null);
  }

  function cancelOnEscape(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      finish(null);
    }
  }

  return (
    <form onSubmit={save}>
      <input
        aria-label="Conversation title"
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={cancelOnEscape}
        onBlur={() => save()}
        onFocus={(event) => event.currentTarget.select()}
        autoFocus
        maxLength={200}
        className="w-full rounded-md border border-emerald-700 px-3 py-2 text-sm focus:outline-none"
      />
    </form>
  );
}

function ConfirmDelete({
  title,
  onCancel,
  onConfirm,
}: {
  title: string;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-10 flex items-center justify-center bg-stone-900/40 p-4"
      onClick={onCancel}
    >
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="delete-heading"
        aria-describedby="delete-description"
        onClick={(event) => event.stopPropagation()}
        onKeyDown={(event) => {
          if (event.key === "Escape") onCancel();
        }}
        className="w-full max-w-sm rounded-lg bg-white p-5 shadow-lg"
      >
        <h2 id="delete-heading" className="font-semibold">
          Delete this conversation?
        </h2>
        <p id="delete-description" className="mt-2 text-sm text-stone-600">
          "{title}" and all its questions and answers will be deleted permanently. This can't be
          undone.
        </p>
        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            autoFocus
            className="rounded-md border border-stone-300 px-3 py-2 text-sm font-medium hover:bg-stone-100"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="rounded-md bg-red-700 px-3 py-2 text-sm font-medium text-white hover:bg-red-800"
          >
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}

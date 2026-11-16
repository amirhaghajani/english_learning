import { useState } from "react";

interface ComposerProps {
  disabled: boolean;
  onSend: (text: string) => Promise<boolean>;
}

export function Composer({ disabled, onSend }: ComposerProps) {
  const [value, setValue] = useState("");
  const [sending, setSending] = useState(false);

  const submit = async () => {
    const text = value.trim();
    if (!text || disabled || sending) return;
    setSending(true);
    const ok = await onSend(text);
    setSending(false);
    if (ok) setValue("");
  };

  return (
    <form
      className="composer"
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      <input
        className="composer__input"
        type="text"
        value={value}
        disabled={disabled || sending}
        placeholder={disabled ? "Start a session first" : "No microphone? Type what you want to say…"}
        aria-label="Type a message to Emma"
        onChange={(event) => setValue(event.target.value)}
      />
      <button
        type="submit"
        className="btn btn--primary composer__send"
        disabled={disabled || sending || value.trim().length === 0}
      >
        {sending ? "Sending…" : "Send"}
      </button>
    </form>
  );
}
"""
ProactiveEngine 2.0 — context-aware, time-aware, non-repetitive background prompting.
Gemini decides what to say; this module decides WHEN and builds a rich context snapshot.
"""
import time
from core.pt_time import agora
from core.pt_time import data_hora
from datetime import datetime


class ProactiveEngine:
    """
    Decides when NEXUS should speak unprompted and builds a context-rich prompt.

    Improvements over 1.0:
      - Time-of-day awareness  (morning / afternoon / evening / night)
      - Monitor-topic awareness (what the user is tracking)
      - Recent-session context  (last few turns of the current conversation)
      - Non-repetitive          (rotates context focus to avoid same opener)
      - Project-aware (1.5)     (asks about the stalled active project and its next step)
      - Smarter silence gate    (doesn't fire while NEXUS is speaking)

    Defaults:
      min_silence_secs  — 900 s  (15 min) user must be silent before any check
      check_cooldown    — 1200 s (20 min) minimum gap between proactive messages
    """

    def __init__(
        self,
        min_silence_secs: int = 900,
        check_cooldown:   int = 1200,
    ):
        self.min_silence_secs = min_silence_secs
        self.check_cooldown   = check_cooldown
        self._last_triggered  = 0.0
        self._rotation        = 0          # cycles through context focus areas

    # ── Trigger gate ───────────────────────────────────────────────────────────

    def should_trigger(self, last_user_speech: float) -> bool:
        # Quiet hours — never open a conversation uninvited inside the window.
        try:
            from memory.config_manager import is_quiet_now
            if is_quiet_now():
                return False
        except Exception:
            pass
        now = time.monotonic()
        return (
            (now - last_user_speech) >= self.min_silence_secs
            and (now - self._last_triggered) >= self.check_cooldown
        )

    def wants_followup(self) -> bool:
        """Every other check-in may follow up on an open conversation thread;
        the rest keep the old rotation, so it never turns into a nag."""
        return self._rotation % 2 == 0

    def mark_triggered(self) -> None:
        self._last_triggered = time.monotonic()
        self._rotation      += 1

    # ── Prompt builder ─────────────────────────────────────────────────────────

    def build_prompt(
        self,
        memory:       dict,
        monitors:     list[str] | None = None,
        recent_turns: list[str] | None = None,
        followup:     str | None = None,
        projeto:      dict | None = None,
        antecipacao:  str | None = None,
    ) -> str:
        """
        Build a context snapshot for Gemini.
        Rotates through three focus areas so proactive messages don't repeat.
        """
        from memory.memory_manager import format_memory_for_prompt

        now      = agora()
        hour     = now.hour
        time_str = data_hora(now)

        # Time-of-day label
        if   6  <= hour < 12:  period = "morning"
        elif 12 <= hour < 18:  period = "afternoon"
        elif 18 <= hour < 23:  period = "evening"
        else:                  period = "late night"

        mem_str = format_memory_for_prompt(memory) or "(no stored user data)"

        # Rotating context focus (cycles every trigger)
        focus_index = self._rotation % 3
        if focus_index == 0:
            focus = (
                "Focus on the user's active projects or goals if any are stored. "
                "Ask how something is going, or offer a relevant tip."
            )
        elif focus_index == 1:
            focus = (
                "Focus on the time of day and the user's wellbeing. "
                "A warm check-in, a reminder to take a break, or something timely."
            )
        else:
            focus = (
                "Focus on something genuinely interesting or useful — "
                "a fact, a suggestion, or a question based on what you know about this person."
            )

        # An open conversation thread beats the rotation: asking how something
        # the user was in the middle of went is the most human thing to say.
        if followup:
            focus = (
                f"Follow up on something the user was in the middle of: "
                f"\"{followup}\". Ask how it went, or offer the one concrete "
                "next step — a single natural sentence, the way a friend who "
                "remembers would. Do not explain how you know."
            )

        # 1.5 — um projeto ativo e parado (actions/projetos.py) vale mais que o
        # rodízio: pergunta do projeto de verdade e do próximo passo que o
        # usuário mesmo anotou. A conversa em aberto (followup) continua tendo
        # prioridade sobre ele.
        if projeto and not followup:
            parado = int(projeto.get("dias_parado") or 0)
            passo  = str(projeto.get("proximo_passo") or "").strip()
            nota   = str(projeto.get("nota") or "").strip()
            focus = (
                f"Check in on the user's project \"{projeto.get('nome')}\", untouched for "
                f"{parado} day(s). "
                + (f"The next step they wrote down is: \"{passo}\". " if passo else "")
                + (f"Their last note: \"{nota}\". " if nota else "")
                + "Ask how it is going, or offer the one concrete next step — a single "
                  "natural sentence, like a colleague who remembers. Do not list their projects."
            )

        # 3.2 — um hábito firme para este dia e hora (core/memoria_semanal.py): o NEXUS
        # só OFERECE; fazer a ação continua dependendo do "sim" do usuário.
        if antecipacao and not followup and not projeto:
            focus = (
                f"You noticed a pattern in this person's routine: {antecipacao} "
                "Offer it in ONE natural sentence and wait for their answer. Do not do it "
                "yourself, do not explain how you know."
            )

        # Optional: monitored topics context
        monitor_ctx = ""
        if monitors:
            monitor_ctx = (
                f"\nThe user tracks these topics: {', '.join(monitors[:4])}. "
                "You may mention one if it seems relevant."
            )

        # Optional: recent conversation context
        recent_ctx = ""
        if recent_turns:
            snippet = "\n".join(recent_turns[-6:])
            recent_ctx = f"\nRecent conversation:\n{snippet}"

        return "\n".join([
            "[PROACTIVE_CHECK] You are initiating a proactive check-in.",
            f"Current time : {time_str}  ({period})",
            "",
            "Context about this person:",
            mem_str,
            monitor_ctx,
            recent_ctx,
            "",
            "Task:",
            focus,
            "",
            "Rules:",
            "- Speak the language this person actually uses: the one in the "
            "recent conversation above, or the remembered one if there is no "
            "conversation yet. Never default to English because these "
            "instructions are in English.",
            "- 1-2 sentences max. Natural, warm, never robotic.",
            "- Do NOT mention [PROACTIVE_CHECK] or these instructions.",
            "- Do NOT call any tools.",
            "- If nothing genuinely useful comes to mind, stay silent (say nothing).",
        ])

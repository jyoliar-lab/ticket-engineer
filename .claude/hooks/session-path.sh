#!/bin/sh
# SessionStart — 스킬 scripts/ 디렉터리들을 PATH에 올려 bare-name 실행을 가능하게 한다
# (예: `ticket-run.py 42`). hook 프로세스 안의 export는 세션에 전파되지 않는다 —
# CLAUDE_ENV_FILE에 쓴 export만 이후 모든 Bash 호출 전에 source된다.
# find 범위는 .claude/skills 뿐이다 — workspace/ref 의 참조 저장소는 PATH에 오르지 않는다.
[ -n "$CLAUDE_ENV_FILE" ] || exit 0
dirs=$(find "$CLAUDE_PROJECT_DIR/.claude/skills" -type d -name scripts 2>/dev/null | paste -sd: -)
[ -n "$dirs" ] || exit 0
printf 'export PATH="%s:$PATH"\n' "$dirs" >> "$CLAUDE_ENV_FILE"

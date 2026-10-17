alias claude-unbound='run-agent --no-sandbox claude'
alias claude='run-agent claude'
alias codex-unbound='run-agent --no-sandbox codex --sandbox danger-full-access --ask-for-approval on-request'
alias codex='run-agent codex --sandbox danger-full-access --ask-for-approval on-request'
alias copilot-unbound='run-agent --no-sandbox copilot --allow-all'
alias copilot='run-agent copilot --allow-all'
alias kiro-unbound='run-agent --no-sandbox kiro-cli chat --trust-all-tools'
alias kiro='run-agent kiro-cli chat --trust-all-tools'
alias pi-unbound='run-agent --no-sandbox pi'
alias pi='run-agent pi'
# A function beats PATH lookup: agents can write the mise dirs ahead of ~/bin (PRD 00160).
warrant() { "$HOME/bin/warrant" "$@"; }

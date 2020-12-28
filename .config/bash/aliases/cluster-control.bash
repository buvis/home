alias update-mopidy-hall='kubectl rollout restart deployment mopidy-hall -n mopidy'
alias get-buvis-temp="ansible-playbook $HOME/git/src/gitlab.com/buvis/playbooks/get-cpu-temperature.yml"
alias update-buvis-nodes="ansible-playbook $HOME/git/src/gitlab.com/buvis/playbooks/upgrade-arch.yml"

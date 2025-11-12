alias solve-merge-conflict="goose run --interactive --provider openrouter --model anthropic/claude-sonnet-4.5 -t \"I have a merge conflict now, but I don't understand why. Can you check?\""
alias auto-commit="goose run --provider openrouter --model anthropic/claude-haiku-4.5 -t \"Check the staged changes and commit them with canonical commit message.\""
alias organize-downloads="goose run --recipe ~/.config/goose/recipes/organize-business-documents.yaml --params downloads=~/Downloads/ --params target=~/bim/reference/local/20-areas/business/ --interactive"

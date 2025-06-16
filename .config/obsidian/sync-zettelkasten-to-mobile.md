## Prepare

1. Create `bim` vault in Obsidian
2. Install and run a-shell
3. Bookmark Obsidian folder: `pickFolder` and select Obsidian
4. Rename bookmark: `renamemark Documents obsidian`
5. Bookmark bim folder: `pickFolder` and select `bim` within Obsidian

## Generate SSH keypair

1. Generate the keypair: `ssh-keygen -t ed25519 -C "tomas@buvis.net"`, no need to set password
2. Go to the key location: `cd` to root, `cd .ssh`
3. Get the public key: `head id_ed25519.pub`
4. Copy the output to clipboard
5. Add the public key to GitHub/GitLab

## Get vault

1. In GitHub/GitLab, find the **SSH URL** for cloning the repository with `bim` vault
2. In a-shell, go to `bim` vault: `jump bim`
3. Remove `.obsidian` as it will be replaced from repository: `rm -rf .obsidian`
4. Clone the repository: `lg2 clone <url_from_step_1> .` (that dot at the end is important, it means "clone to current directory")
5. Persist the credentials: `lg2 config user.identityFile "~/Documents/.ssh/id_ed25519"` and `lg2 config user.password “”`
6. Set identity for signing commits: `lg2 config user.name "Tomáš Bouška"` and `lg2 config user.email "tomas@buvis.net"`

## Create shortcuts and automations

1. Open Shortcuts - Automation
2. Create following automations:
   1. At specific time (different per device), daily = Obsidian: safe sync
   2. When I arrive home = Obsidian: safe sync
   3. When I leave home = Obsidian: safe sync
   4. When "Obsidian" is closed = Obsidian: safe sync

### Shortcuts actions backup

#### Obsidian: safe sync

Execute a-shell command

1. jump bim
2. lg2 stash
3. lg2 pull
4. lg2 stash pop
5. lg2 add .
6. lg2 commit -m "Sync on <Current Date> from <Device Hostname>"
7. lg2 push
8. exit

#### Obsidian: pull

Execute a-shell command

1. jump bim
2. lg2 pull
3. exit

#### Obsidian

1. Run shortcut `Obsidian: pull`
2. Open `Obsidian`

## References

- [My Git backup workflow on iOS (better than Working Copy)](https://forum.obsidian.md/t/my-git-backup-workflow-on-ios-better-than-working-copy/52966)
- [Automatic sync with GitHub on iOS (for free) via a-shell](https://forum.obsidian.md/t/mobile-automatic-sync-with-github-on-ios-for-free-via-a-shell/46150)

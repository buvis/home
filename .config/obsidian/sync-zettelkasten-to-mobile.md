1. Create `zettelkasten` vault in Obsidian
2. Use mobile settings: Settings - About - Advanced - Override config folder to `.obsidian-mobile`
3. Install [Working Copy - Git client](https://apps.apple.com/us/app/working-copy-git-client/id896694807)
4. Add zettelkasten repository in Working Copy:
    1. Repositories - + - Setup synced directory - On My iPad/iPhone/Obsidian/Zettelkasten
    2. Repository - Remotes - Add Remote
        1. URL = https://gitlab.com/buvis/zettelkasten
        2. Test
        3. Synchronize
        4. Username = tbouska
        5. Password = <generate token at https://gitlab.com/-/profile/personal_access_tokens>
    3. Create commit identity: Repository - Current - Configuration - +
    4. Pull
    5. Revert local changes
5. Add "Backup Obsidian via Working Copy" to Home Screen
6. Create automation to run "Backup Obsidian via Working Copy" shortcut when Obsidian is closed
7. Add "Open Obsidian" to Home Screen and use it instead of Obsidian's icon

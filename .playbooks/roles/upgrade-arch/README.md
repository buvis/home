Upgrade Arch OS
===============

This role updates Arch Linux system packages.

Requirements
------------

Host must be running Arch Linux ;)

Role Variables
--------------

No variables.

Dependencies
------------

No dependencies.

Example Playbook
----------------

```
- hosts: all
  remote_user: "{{ default_user }}"
  become: true
  gather_facts: true

  roles:
    - role: upgrade-arch
      when: ansible_distribution == "Archlinux"
```

License
-------

BSD

Author Information
------------------

Authored by Tomáš Bouška (tomas@buvis.net)

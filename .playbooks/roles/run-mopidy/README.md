Run mopidy with pulsesink
=========================

This role installs docker.

Requirements
------------

None.

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
  - install-docker
```

License
-------

BSD

Author Information
------------------

Authored by Tomáš Bouška (tomas@buvis.net)

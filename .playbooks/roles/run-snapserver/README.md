Run Snapcast server
===================

This role runs Snapcast server in Docker container.

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
  - run-snapserver
```

License
-------

BSD

Author Information
------------------

Authored by Tomáš Bouška (tomas@buvis.net)

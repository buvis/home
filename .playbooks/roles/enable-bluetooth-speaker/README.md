Enable Bluetooth speaker
========================

Add support to play audio through Bluetooth speaker.

Requirements
------------

None.

Role Variables
--------------

None.

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
  - enable-bt-speaker
```

License
-------

BSD

Author Information
------------------

Authored by Tomáš Bouška (tomas@buvis.net)

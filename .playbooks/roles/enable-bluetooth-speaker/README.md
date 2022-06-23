Install snapclient on a raspberry
=================================

This role installs the latest snapclient from https://github.com/badaix/snapcast/releases for armhf.

Requirements
------------

None.

Role Variables
--------------

- url_snaplcient_armhf_deb
- ip_snapserver

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

  pre_tasks:
  - pause:
      prompt: Enter IP address of snapserver
    register: ip_snapserver

  roles:
  - install-snapclient
```

License
-------

BSD

Author Information
------------------

Authored by Tomáš Bouška (tomas@buvis.net)

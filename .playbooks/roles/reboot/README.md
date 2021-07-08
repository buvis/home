Reboot
======

Reboot and wait for SSH to be ready.

Requirements
------------

None.

Role Variables
--------------

None.

Dependencies
------------

None.

Example Playbook
----------------

Reboot all hosts:

```
- hosts: all
  become: true

  roles:
    - role: reboot
```

License
-------

BSD

Author Information
------------------

Authored by Tomáš Bouška (https://buvis.net)

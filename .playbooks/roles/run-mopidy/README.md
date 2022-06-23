Run Mopidy
==========

This role runs Mopidy in Docker container.


Requirements
------------

None.

Role Variables
--------------

- nas_media_directory: set it to NFS destination as <NAS_IP>:/mnt/tank/media/music

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
      prompt: Enter NAS mount point for Mopidy media directory (<NAS_IP>:/mnt/tank/media/music) or leave empty to skip
    register: nas_media_directory

  roles:
  - run-mopidy
```

License
-------

BSD

Author Information
------------------

Authored by Tomáš Bouška (tomas@buvis.net)

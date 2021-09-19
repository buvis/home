## Create recoverable volume
1. Create volume in Longhorn UI, either empty or as a restore from backup
2. Refer to it from manifest files:
  ```yaml
  ---
  apiVersion: v1
  kind: PersistentVolume
  metadata:
    name: <VOLUME_NAME>  # same as in Longhorn UI
  spec:
    capacity:
      storage: 10Gi  # same as in Longhorn UI
    volumeMode: Filesystem
    accessModes:
    - ReadWriteOnce
    persistentVolumeReclaimPolicy: Retain
    csi:
      driver: driver.longhorn.io
      fsType: ext4
      volumeAttributes:
        numberOfReplicas: "2"  # same as in Longhorn UI
        staleReplicaTimeout: "30"
      volumeHandle: <VOLUME_NAME>  # this points to existing volume in Longhorn, make sure it was created in step 1
    storageClassName: longhorn
    claimRef:
      apiVersion: v1
      kind: PersistentVolumeClaim
      name: <PVC_NAME>
      namespace: <PVC_NAMESPACE>
  ---
  apiVersion: v1
  kind: PersistentVolumeClaim
  metadata:
    name: <PVC_NAME>
    namespace: <PVC_NAMESPACE>
  spec:
    storageClassName: longhorn
    accessModes:
    - ReadWriteOnce
    resources:
      requests:
        storage: 10Gi  # same as in Longhorn UI
  ```

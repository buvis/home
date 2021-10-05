# Purpose
All you need to run [Mopidy](https://docs.mopidy.com/en/latest/) in a container.

# Instructions

## Prepare
The configuration file `mopidy.conf` must exist in the same folder as Dockerfile. Follow [Mopidy's official documentation](https://docs.mopidy.com/en/latest/config/) to create it from scratch. As the configuration file will likely contain secrets, use git-secrets to keep it in version control system and never push the resulting image to a public registry.

## Build

### On arm
`docker build -t mopidy .`

### On non-arm platform
1. Start emulation: `docker run --rm --privileged multiarch/qemu-user-static --reset -p yes`
2. Cross build: `docker buildx build --no-cache --platform linux/arm/v6 -t mopidy .`

## Run

### Before the first execution
1. `sudo pacman -S aws-cli docker`
2. `sudo systemctl enable docker && sudo systemctl start docker`
3. `sudo usermod -a -G docker bob`
4. `sudo mkdir -p {/var/local/docker/mopidy/local,/var/local/docker/mopidy/media,/var/local/docker/mopidy/playlists}`
5. `sudo useradd mopidy -u 105`
6. `sudo chown -R 105:staff /var/local/docker/mopidy`
7. `aws configure`

### Afterwards
```
docker run --detach --restart=always \
  -p 6680:6680 -p 6600:6600 \
  --device /dev/snd \
  --mount type=bind,source=/var/local/docker/mopidy/media,target=/var/lib/mopidy/media,readonly \
  --mount type=bind,source=/var/local/docker/mopidy/local,target=/var/lib/mopidy/local \
  --mount type=bind,source=/var/local/docker/mopidy/playlists,target=/var/lib/mopidy/playlists \
  --name mopidy \
   mopidy
```

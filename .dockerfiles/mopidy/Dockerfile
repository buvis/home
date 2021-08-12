FROM debian:stable-slim
ENV DEBIAN_FRONTEND=noninteractive

# Add Mopidy to sources
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        ca-certificates \
        gnupg2 \
        sudo \
        wget \
 && wget -q -O mopidy.key https://apt.mopidy.com/mopidy.gpg \
 && apt-key add mopidy.key \
 && wget -q -O /etc/apt/sources.list.d/mopidy.list https://apt.mopidy.com/buster.list \
 && apt-get purge -y wget \
 && apt-get autoremove -y \
 && apt-get clean -y \
 && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* ~/.cache

# Install codecs
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        gstreamer1.0-alsa \
        gstreamer1.0-plugins-base \
        gstreamer1.0-plugins-bad \
        gstreamer1.0-plugins-good \
        gstreamer1.0-plugins-ugly \
        gstreamer1.0-libav \
 && apt-get autoremove -y \
 && apt-get clean -y \
 && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* ~/.cache

# Install Mopidy and extensions
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        mopidy \
        mopidy-mpd \
        mopidy-local \
        mopidy-scrobbler \
        mopidy-spotify \
        mopidy-soundcloud \
        mopidy-tunein \
        python3-pip \
        python3-setuptools \
 && python3 -m pip install \
        Mopidy-DefaultPlaylist \
        Mopidy-Iris \
        Mopidy-MPD \
        Mopidy-Youtube \
 && apt-get autoremove -y \
 && apt-get clean -y \
 && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* ~/.cache \
 && update-ca-certificates -f \
 && echo "mopidy ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/mopidy-is-superuser

# Supply the configuration
COPY mopidy.conf /etc/mopidy/mopidy.conf

# Create volumes
VOLUME ["/var/lib/mopidy/local", "/var/lib/mopidy/media", "/var/lib/mopidy/playlists"]

# Open the ports
EXPOSE 6680 6600

# Start Mopidy
CMD mopidy --config /etc/mopidy/mopidy.conf

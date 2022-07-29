cite about-plugin
about-plugin 'functions for backing stuff up'

# backup router configuration
function backup-router () {
    mkdir -p $DOTFILES_ROOT/Downloads/router-backup
    cd $DOTFILES_ROOT/Downloads/router-backup
    mkdir -p etc
    mkdir -p etc/mail
    mkdir -p etc/protonvpn
    mkdir -p etc/ssh
    mkdir -p home/bob
    mkdir -p var/unbound/etc
    scp orcus:/etc/bgpd.conf etc/bgpd.conf
    scp orcus:/etc/dhclient.conf etc/dhclient.conf
    scp orcus:/etc/dhcpd.conf etc/dhcpd.conf
    scp orcus:/etc/dnscrypt-proxy-buvis.toml etc/dnscrypt-proxy-buvis.toml
    scp orcus:/etc/dnscrypt-proxy.toml etc/dnscrypt-proxy.toml
    scp orcus:/etc/hostname.em0 etc/hostname.em0
    scp orcus:/etc/hostname.em1 etc/hostname.em1
    scp orcus:/etc/hostname.em2 etc/hostname.em2
    scp orcus:/etc/hostname.bridge0 etc/hostname.bridge0
    scp orcus:/etc/hosts etc/hosts
    scp orcus:/etc/mail/smtpd.conf etc/mail/smtpd.conf
    scp orcus:/etc/newsyslog.conf etc/newsyslog.conf
    scp orcus:/etc/pf.conf etc/pf.conf
    scp -r orcus:/etc/protonvpn/ etc/protonvpn/
    scp orcus:/etc/rc.conf.local etc/rc.conf.local
    scp orcus:/etc/resolv.conf.tail etc/resolv.conf.tail
    scp orcus:/etc/ssh/sshd_config etc/ssh/sshd_config
    scp orcus:/etc/sysctl.conf etc/ssh/sysctl.conf
    scp orcus:/home/bob/send-vim-tip.sh home/bob/send-vim-tip.sh
    scp -r orcus:/var/unbound/etc/ var/unbound/
    cd -
}

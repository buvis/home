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
    mkdir -p usr/local/bin
    scp orcus.buvis.net:/etc/bgpd.conf etc/bgpd.conf
    scp orcus.buvis.net:/etc/dhclient.conf etc/dhclient.conf
    scp orcus.buvis.net:/etc/dhcpd.conf etc/dhcpd.conf
    scp orcus.buvis.net:/etc/dnscrypt-proxy-buvis.toml etc/dnscrypt-proxy-buvis.toml
    scp orcus.buvis.net:/etc/dnscrypt-proxy.toml etc/dnscrypt-proxy.toml
    scp orcus.buvis.net:/etc/hostname.em0 etc/hostname.em0
    scp orcus.buvis.net:/etc/hostname.em1 etc/hostname.em1
    scp orcus.buvis.net:/etc/hostname.em2 etc/hostname.em2
    scp orcus.buvis.net:/etc/hostname.bridge0 etc/hostname.bridge0
    scp orcus.buvis.net:/etc/hosts etc/hosts
    scp orcus.buvis.net:/etc/mail/smtpd.conf etc/mail/smtpd.conf
    scp orcus.buvis.net:/etc/newsyslog.conf etc/newsyslog.conf
    scp orcus.buvis.net:/etc/pf.conf etc/pf.conf
    scp -r orcus.buvis.net:/etc/protonvpn/ etc/protonvpn/
    scp orcus.buvis.net:/etc/rc.conf.local etc/rc.conf.local
    scp orcus.buvis.net:/etc/resolv.conf.tail etc/resolv.conf.tail
    scp orcus.buvis.net:/etc/ssh/sshd_config etc/ssh/sshd_config
    scp orcus.buvis.net:/etc/sysctl.conf etc/ssh/sysctl.conf
    scp orcus.buvis.net:/home/bob/send-vim-tip.sh home/bob/send-vim-tip.sh
    scp orcus.buvis.net:/usr/local/bin/reload_abusers.sh usr/local/bin/reload_abusers.sh
    scp -r orcus.buvis.net:/var/unbound/etc/ var/unbound/
    cd -
}

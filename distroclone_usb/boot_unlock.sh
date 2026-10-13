#!/bin/sh
# Trusted supplemental initramfs script. Contains no password or key material.
case "${1:-}" in prereqs) echo ""; exit 0;; esac
. /scripts/functions

fail_closed() {
    unset dcusb_secret
    panic "$failure"
    # panic may return after an emergency shell; never continue into live discovery.
    while :; do sleep 3600; done
}

prompt='distroClone USB: enter USB passphrase: '
failure='distroClone USB: encrypted volumes could not be unlocked. Reboot to retry.'
language=en
data_uuid=
persist_uuid=
for argument in $(cat /proc/cmdline); do
    case "$argument" in
        dcusb.lang=*) language=${argument#*=} ;;
        dcusb.data-uuid=*) data_uuid=${argument#*=} ;;
        dcusb.persist-uuid=*) persist_uuid=${argument#*=} ;;
    esac
done
[ -n "$data_uuid$persist_uuid" ] || exit 0
case "$language" in
    it) prompt='distroClone USB: inserisci la frase segreta USB: '
        failure='distroClone USB: impossibile sbloccare i volumi cifrati. Riavvia per riprovare.' ;;
    es) prompt='distroClone USB: introduce la frase secreta USB: '
        failure='distroClone USB: no se pudieron desbloquear los volúmenes cifrados. Reinicia para reintentar.' ;;
    fr) prompt='distroClone USB : saisissez la phrase secrète USB : '
        failure='distroClone USB : impossible de déverrouiller les volumes chiffrés. Redémarrez pour réessayer.' ;;
    de) prompt='distroClone USB: USB-Passphrase eingeben: '
        failure='distroClone USB: verschlüsselte Volumes konnten nicht entsperrt werden. Zum Wiederholen neu starten.' ;;
esac

for volume_uuid in "$data_uuid" "$persist_uuid"; do
    [ -n "$volume_uuid" ] || continue
    case "$volume_uuid" in *[!0-9a-f-]*) fail_closed;; esac
    [ "${#volume_uuid}" -eq 36 ] || fail_closed
    count=0
    while [ ! -b "/dev/disk/by-uuid/$volume_uuid" ]; do
        count=$((count + 1))
        [ "$count" -lt 30 ] || fail_closed
        sleep 1
    done
done
modprobe dm_crypt || fail_closed
askpass=/usr/lib/cryptsetup/askpass
[ -x "$askpass" ] || askpass=/lib/cryptsetup/askpass
[ -x "$askpass" ] || fail_closed

open_volume() {
    [ -n "$1" ] || return 0
    [ ! -e "/dev/mapper/$2" ] || return 1
    printf '%s' "$dcusb_secret" | cryptsetup open --type luks --key-file=- \
        "/dev/disk/by-uuid/$1" "$2" >/dev/console 2>&1
}

for attempt in 1 2 3; do
    dcusb_secret=$("$askpass" "$prompt" 2>/dev/console) || fail_closed
    if open_volume "$data_uuid" dcusb_data; then
        if open_volume "$persist_uuid" dcusb-persist; then
            unset dcusb_secret
            exit 0
        fi
        [ -z "$data_uuid" ] || cryptsetup close dcusb_data
    fi
    unset dcusb_secret
done
fail_closed

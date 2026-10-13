# File copiati nella partizione persistente da un altro sistema

## Verifica sulla USB fisica — 13 ottobre 2026
La chiavetta dell'utente avvia correttamente un altro PC. Sul sistema installato
sono stati copiati quattro pacchetti nella radice del volume persistente:

- advanced-comics-converter_2.3.0_all.deb
- distroclone-usb_0.1.0_all.deb
- rename-comics-universal_3.2.1_all.deb
- syslinuxos-boot-repair_0.3.1_amd64.deb

Ispezione in sola lettura: tutti e quattro i file presenti, partizione ext4 da
8 GiB, `persistence.conf` contenente `/ union`, directory `rw` e `work` presenti.
Il menu GRUB predefinito abilita `persistence` e seleziona l'etichetta corretta.
Nessuna modifica ai file, alla configurazione o alle partizioni eseguita.

## Perché i file non compaiono nella Home della live
La persistenza del sistema usa `rw` come livello scrivibile dell'overlay. I file
copiati direttamente nella radice del volume rimangono esterni a quel livello.
Inoltre il volume già usato dalla live può non comparire come disco separato nel
gestore file; l'assenza di una voce laterale non dimostra che la persistenza sia
disattivata.

Nella live aprire il gestore file, premere **Ctrl+L** e inserire:

```text
/run/live/persistence
```

Aprire la cartella della partizione USB (il nome dipende dal PC, per esempio
`sda4` o `sdb4`). I quattro `.deb` si trovano nella sua radice, se la persistenza
è stata attivata. Copiarli da lì in Documenti per trovarli nella normale sessione.
Le copie effettuate in Documenti durante una sessione persistente vengono salvate
dal sistema nella struttura corretta.

Per distinguere una partizione non mostrata da una persistenza non attiva, sulla
live verificare `findmnt /` e `findmnt -t ext4`: il livello scrivibile di `/` deve
usare il volume persistente. Le prove precedenti in VM hanno mostrato
`upperdir=/run/live/persistence/sda4/rw`.

La sessione live sull'altro PC non è stata ispezionata direttamente. La verifica
fisica qui documentata riguarda contenuto e configurazione della USB.

Fonte: https://manpages.debian.org/trixie/live-boot-doc/persistence.conf.5.en.html

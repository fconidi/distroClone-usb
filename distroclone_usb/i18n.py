"""Small desktop translation catalog; locale follows the user's session."""

import locale
import os

LANGUAGE = next((os.environ[key] for key in ('LANGUAGE', 'LC_ALL', 'LC_MESSAGES', 'LANG')
                 if os.environ.get(key)), locale.getlocale()[0] or 'en')
ITALIAN = LANGUAGE.startswith('it')
IT = {
    'Create a persistent live USB': 'Crea una USB live persistente',
    'Your system, ready to travel.': 'Il tuo sistema, pronto a partire.',
    '1. Live ISO': '1. ISO live',
    'Choose an ISO image': 'Scegli una immagine ISO',
    'Choose a Debian Live, SysLinuxOS, Ubuntu or Linux Mint desktop ISO.':
        'Scegli una ISO desktop Debian Live, SysLinuxOS, Ubuntu o Linux Mint.',
    '2. USB drive': '2. Chiavetta USB',
    'Refresh': 'Aggiorna',
    'Unmount volumes': 'Smonta volumi',
    'No USB drive found. Connect one and refresh.': 'Nessuna USB trovata. Collegane una e aggiorna.',
    'Select a USB drive explicitly.': 'Seleziona una chiavetta USB.',
    '3. Persistence': '3. Persistenza',
    'GiB reserved for applications, settings and files.': 'GiB riservati a programmi, impostazioni e file.',
    'All existing USB data will be erased. Secure Boot must be disabled.':
        'Tutti i dati sulla USB saranno cancellati. Secure Boot deve essere disattivato.',
    'Create USB…': 'Crea USB…',
    'Ready. Choose an ISO and a USB drive.': 'Pronto. Scegli una ISO e una chiavetta USB.',
    'Inspecting ISO and computing SHA-256…': 'Analisi ISO e calcolo SHA-256…',
    'ISO recognized': 'ISO riconosciuta',
    'Error': 'Errore',
    'Erase and create USB': 'Cancella e crea USB',
    'Cancel': 'Annulla',
    'This permanently erases every partition and file on:': 'Cancella definitivamente tutte le partizioni e i file su:',
    'Type the device name to confirm:': 'Digita il nome del dispositivo per confermare:',
    'Authentication / validating ISO': 'Autenticazione / verifica ISO',
    'Partitioning and formatting': 'Partizionamento e formattazione',
    'Copying ISO': 'Copia della ISO',
    'Verifying USB copy': 'Verifica della copia USB',
    'Installing BIOS / UEFI boot': 'Installazione avvio BIOS / UEFI',
    'USB created and verified. You can disconnect it.': 'USB creata e verificata. Puoi scollegarla.',
    'Creation failed. The USB may be incomplete.': 'Creazione fallita. La USB può essere incompleta.',
    'USB creation is running. Please wait before closing.': 'Creazione USB in corso. Attendi prima di chiudere.',
    'Install the Debian package before creating a USB.': 'Installa il pacchetto Debian prima di creare una USB.',
    'Authorization was cancelled or the writer could not start.': 'Autorizzazione annullata o scrittura non avviata.',
    'Cannot start the USB writer.': 'Impossibile avviare la scrittura USB.',
    'Operation log': 'Registro operazione',
    'ISO': 'ISO',
    'Profile': 'Profilo',
    'Persistence': 'Persistenza',
    'Volumes mounted: unmount before creating the USB.': 'Volumi montati: smontali prima di creare la USB.',
    'USB ready': 'USB pronta',
    'Details': 'Dettagli',
}


def tr(text):
    return IT.get(text, text) if ITALIAN else text

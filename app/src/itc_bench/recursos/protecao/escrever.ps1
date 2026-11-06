# Proteção do login (ADR-022): escritas fixas no registro, sem dado de fora.
# $env:ITC_ACAO = atalho_desligar | atalho_padrao | remover_depurador. Saída: OK ou ERRO|codigo.
$Vista = [Microsoft.Win32.RegistryView]::Registry64
$EXES = @('utilman.exe', 'sethc.exe', 'osk.exe', 'Magnify.exe', 'Narrator.exe', 'DisplaySwitch.exe', 'AtBroker.exe')
$IFEO = 'SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options'
$SPE = 'SOFTWARE\Microsoft\Windows NT\CurrentVersion\SilentProcessExit'
# (chave, desligado, padrão do Windows) das flags do Shift 5x na tela de login.
$FLAGS = @(@('StickyKeys', '506', '510'), @('Keyboard Response', '122', '126'), @('ToggleKeys', '58', '62'))

function Falhar([string]$codigo) { Write-Output ('ERRO|' + $codigo); exit 1 }

switch ($env:ITC_ACAO) {
    { $_ -in @('atalho_desligar', 'atalho_padrao') } {
        $i = if ($env:ITC_ACAO -eq 'atalho_desligar') { 1 } else { 2 }
        try {
            $u = [Microsoft.Win32.RegistryKey]::OpenBaseKey('Users', $Vista)
            foreach ($f in $FLAGS) {
                $k = $u.CreateSubKey('.DEFAULT\Control Panel\Accessibility\' + $f[0], $true)
                $k.SetValue('Flags', $f[$i], 'String')
                $k.Close()
            }
            $u.Close()
        } catch { Falhar $_.Exception.GetType().Name }
        Write-Output 'OK'
    }
    'remover_depurador' {
        # Só Debugger (chave do exe e subchaves) e MonitorProcess, só dos 7 exes fixos.
        try {
            $maq = [Microsoft.Win32.RegistryKey]::OpenBaseKey('LocalMachine', $Vista)
            foreach ($exe in $EXES) {
                $k = $maq.OpenSubKey("$IFEO\$exe", $true)
                if ($k) {
                    $k.DeleteValue('Debugger', $false)
                    foreach ($n in $k.GetSubKeyNames()) {
                        $s = $k.OpenSubKey($n, $true)
                        if ($s) { $s.DeleteValue('Debugger', $false); $s.Close() }
                    }
                    $k.Close()
                }
                $k = $maq.OpenSubKey("$SPE\$exe", $true)
                if ($k) { $k.DeleteValue('MonitorProcess', $false); $k.Close() }
            }
            $maq.Close()
        } catch { Falhar $_.Exception.GetType().Name }
        Write-Output 'OK'
    }
    default { Falhar 'acao' }
}

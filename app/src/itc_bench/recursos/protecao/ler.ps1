# Proteção do login (ADR-022): só leitura. Para os 7 binários de acessibilidade da tela de login:
# arquivo (assinatura do Windows + nome original), ACL (negar execução ao SYSTEM, dono) e IFEO;
# e as flags do Shift 5x em HKU\.DEFAULT. Saída: JSON. Nunca "trocado" sem a verificação ter rodado.
$Vista = [Microsoft.Win32.RegistryView]::Registry64
$sys = [Environment]::GetFolderPath('System')
$TI = 'S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464'
# exe -> nomes originais aceitos (OriginalFilename, sem .mui), conferidos no Windows 11.
$EXES = [ordered]@{
    'utilman.exe' = @('utilman.exe', 'utilman2.exe'); 'sethc.exe' = @('sethc.exe'); 'osk.exe' = @('osk.exe')
    'Magnify.exe' = @('magnify.exe', 'screenmagnifier.exe'); 'Narrator.exe' = @('narrator.exe', 'sr.exe')
    'DisplaySwitch.exe' = @('displayswitch.exe'); 'AtBroker.exe' = @('atbroker.exe')
}
$IFEO = 'SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options'
$SPE = 'SOFTWARE\Microsoft\Windows NT\CurrentVersion\SilentProcessExit'
$FLAGS = @('StickyKeys', 'Keyboard Response', 'ToggleKeys')

$cripto = $false
try { $cripto = (Get-Service -Name 'CryptSvc' -ErrorAction Stop).Status -eq 'Running' } catch { $cripto = $false }

function Tem-Valor($k, [string]$nome) {
    $v = $k.GetValue($nome, $null)
    return ($null -ne $v) -and ("$v".Trim() -ne '')
}

function Depurador($maq, [string]$exe) {
    # Debugger na chave do exe ou em qualquer subchave (filtro por caminho: UseFilter fica na chave
    # do exe, FilterFullPath e Debugger na subchave), com ou sem UseFilter; MonitorProcess no SPE.
    $achou = $false
    $k = $maq.OpenSubKey("$IFEO\$exe", $false)
    if ($k) {
        if (Tem-Valor $k 'Debugger') { $achou = $true }
        foreach ($n in $k.GetSubKeyNames()) {
            $s = $k.OpenSubKey($n, $false)
            if ($s) {
                if (Tem-Valor $s 'Debugger') { $achou = $true }
                $s.Close()
            }
        }
        $k.Close()
    }
    $k = $maq.OpenSubKey("$SPE\$exe", $false)
    if ($k) {
        if (Tem-Valor $k 'MonitorProcess') { $achou = $true }
        $k.Close()
    }
    return $achou
}

$maq = [Microsoft.Win32.RegistryKey]::OpenBaseKey('LocalMachine', $Vista)
$bins = @()
foreach ($exe in $EXES.Keys) {
    $r = [ordered]@{ exe = $exe; arquivo = 'nao_lido'; acl = 'nao_lida'; ifeo = 'nao_lido' }
    $p = Join-Path $sys $exe
    if (-not (Test-Path -LiteralPath $p -PathType Leaf)) {
        $r.arquivo = 'ausente'; $r.acl = 'ausente'
    } else {
        if ($cripto) {
            try {
                $a = Get-AuthenticodeSignature -LiteralPath $p
                $orig = ([string](Get-Item -LiteralPath $p).VersionInfo.OriginalFilename) -replace '\.mui$', ''
                $st = [string]$a.Status
                if ($st -eq 'Valid') {
                    $r.arquivo = if ($a.IsOSBinary -and ($EXES[$exe] -contains $orig.ToLowerInvariant())) { 'original' } else { 'trocado' }
                } elseif ($st -in @('NotSigned', 'HashMismatch', 'NotTrusted')) {
                    $r.arquivo = 'trocado'
                }
            } catch { $r.arquivo = 'nao_lido' }
        }
        try {
            $acl = Get-Acl -LiteralPath $p
            $nega = $false
            foreach ($x in $acl.GetAccessRules($true, $false, [Security.Principal.SecurityIdentifier])) {
                if ($x.AccessControlType -eq 'Deny' -and $x.IdentityReference.Value -eq 'S-1-5-18' -and
                    ($x.FileSystemRights -band [Security.AccessControl.FileSystemRights]::ExecuteFile)) { $nega = $true }
            }
            $dono = $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
            $r.acl = if ($dono -ne $TI) { 'dono' } elseif ($nega) { 'protegido' } else { 'livre' }
        } catch { $r.acl = 'nao_lida' }
    }
    try { $r.ifeo = if (Depurador $maq $exe) { 'depurador' } else { 'limpo' } } catch { $r.ifeo = 'nao_lido' }
    $bins += [pscustomobject]$r
}
$maq.Close()

$atalho = @{}
try {
    $u = [Microsoft.Win32.RegistryKey]::OpenBaseKey('Users', $Vista)
    foreach ($f in $FLAGS) {
        $k = $u.OpenSubKey(".DEFAULT\Control Panel\Accessibility\$f", $false)
        $atalho[[string]$f] = if ($k) { $v = $k.GetValue('Flags', $null); $k.Close(); if ($null -eq $v) { $null } else { "$v" } } else { $null }
    }
    $u.Close()
} catch { $atalho = $null }

[pscustomobject]@{ binarios = $bins; flags = $atalho } | ConvertTo-Json -Compress -Depth 4

# Limpeza de contas (ADR-042). ITC_ACAO: previa | limpar. ITC_SIDS: SIDs separados por vírgula.
# ITC_PROTEGIDAS: nomes da Suporte em minúsculas, separados por vírgula.
# Só pastas fixas dentro do perfil; nunca o registro da conta (NTUSER.DAT), nunca segue reparse
# point (o link é removido como link) e cada caminho é conferido contra a raiz. A conta tem de
# estar sem sessão (hive descarregado). Saída só com números por posição da conta, nunca SID,
# nome ou caminho.
$win = [Environment]::GetFolderPath('Windows')
$usuarios = Join-Path ([IO.Path]::GetPathRoot($win)) 'Users'
$RP = [IO.FileAttributes]::ReparsePoint
$apagar = $env:ITC_ACAO -eq 'limpar'
if (-not $apagar -and $env:ITC_ACAO -ne 'previa') { throw 'acao invalida' }
$dono = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$protegidas = @($env:ITC_PROTEGIDAS -split ',' | Where-Object { $_ })

$CATEGORIAS = [ordered]@{
    pessoais    = @('Desktop', 'Documents', 'Downloads', 'Pictures', 'Videos', 'Music', 'Saved Games')
    temporarios = @(
        'AppData\Local\Temp', 'AppData\Local\CrashDumps', 'AppData\Local\D3DSCache',
        'AppData\Local\Microsoft\Windows\INetCache', 'AppData\Local\Microsoft\Windows\WER',
        'AppData\Local\Microsoft\Windows\Explorer')
    navegadores = @(
        'AppData\Local\Microsoft\Edge\User Data\*\Cache', 'AppData\Local\Microsoft\Edge\User Data\*\Code Cache',
        'AppData\Local\Microsoft\Edge\User Data\*\GPUCache', 'AppData\Local\Microsoft\Edge\User Data\*\Service Worker\CacheStorage',
        'AppData\Local\Google\Chrome\User Data\*\Cache', 'AppData\Local\Google\Chrome\User Data\*\Code Cache',
        'AppData\Local\Google\Chrome\User Data\*\GPUCache', 'AppData\Local\Google\Chrome\User Data\*\Service Worker\CacheStorage',
        'AppData\Local\Mozilla\Firefox\Profiles\*\cache2',
        'AppData\Roaming\Microsoft\Teams\Cache', 'AppData\Roaming\Microsoft\Teams\Code Cache',
        'AppData\Roaming\Microsoft\Teams\GPUCache', 'AppData\Roaming\Microsoft\Teams\blob_storage')
    programas   = @('AppData\Local\Programs')
}

function Eh-Reparse([string]$c) {
    $i = Get-Item -LiteralPath $c -Force -ErrorAction SilentlyContinue
    return ($null -ne $i) -and (($i.Attributes -band $RP) -ne 0)
}

function Raizes([string]$perfil, [string]$rel) {
    # Desce parte por parte a partir do perfil; `*` = cada subpasta comum (perfil do navegador).
    $atuais = @($perfil)
    foreach ($parte in ($rel -split '\\')) {
        $proximas = @()
        foreach ($a in $atuais) {
            if ($parte -eq '*') {
                $proximas += @(Get-ChildItem -LiteralPath $a -Force -Directory -ErrorAction SilentlyContinue |
                    Where-Object { ($_.Attributes -band $RP) -eq 0 } | ForEach-Object { $_.FullName })
            } else {
                $c = Join-Path $a $parte
                if ((Test-Path -LiteralPath $c -PathType Container) -and -not (Eh-Reparse $c)) { $proximas += $c }
            }
        }
        $atuais = $proximas
    }
    return $atuais
}

function Varrer([string]$raiz, $acc) {
    $di = New-Object IO.DirectoryInfo $raiz
    if (-not $di.Exists) { return }
    if (($di.Attributes -band $RP) -ne 0) { $acc.codigo = 'reparse'; return }
    $prefixo = $di.FullName.TrimEnd('\') + '\'
    $pilha = New-Object System.Collections.Stack
    $pilha.Push($di)
    $dirs = New-Object System.Collections.ArrayList
    while ($pilha.Count -gt 0) {
        $d = $pilha.Pop()
        try { $itens = @($d.GetFileSystemInfos()) } catch { $acc.em_uso++; continue }
        foreach ($i in $itens) {
            if (-not $i.FullName.StartsWith($prefixo, [StringComparison]::OrdinalIgnoreCase)) { $acc.codigo = 'fora'; continue }
            if (($i.Attributes -band $RP) -ne 0) {
                if ($apagar) {
                    try { if ($i -is [IO.DirectoryInfo]) { [IO.Directory]::Delete($i.FullName, $false) } else { $i.Delete() } }
                    catch { $acc.em_uso++ }
                }
                continue
            }
            if ($i -is [IO.DirectoryInfo]) { $pilha.Push($i); [void]$dirs.Add($i); continue }
            if ($i.Name -ieq 'desktop.ini') { continue }  # nome e ícone da pasta no Explorer
            $acc.arquivos++
            $acc.bytes += $i.Length
            if ($apagar) {
                try { $i.Attributes = [IO.FileAttributes]::Normal; $i.Delete() } catch { $acc.em_uso++ }
            }
        }
    }
    if ($apagar) {
        for ($k = $dirs.Count - 1; $k -ge 0; $k--) {
            try { $dirs[$k].Delete($false) } catch { }  # pasta com arquivo em uso ou desktop.ini fica
        }
    }
}

function Recusa([string]$sid) {
    if ($sid -notmatch '^S-1-5-21-[\d-]+$') { return 'sid_invalido' }
    if ($sid -match '-500$') { return 'nativo' }
    if ($sid -eq $dono) { return 'dono' }
    try {
        $nome = (New-Object Security.Principal.SecurityIdentifier $sid).Translate([Security.Principal.NTAccount]).Value
        $curto = (($nome -split '\\')[-1]).ToLowerInvariant()
        if ($protegidas -contains $curto) { return 'suporte' }
        if (@('gestão', 'gestao') -contains $curto) { return 'restrita' }  # ADR-036
    } catch { }
    if (Test-Path -LiteralPath ('Registry::HKEY_USERS\' + $sid)) { return 'sessao' }
    $k = Get-Item -LiteralPath ('HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\' + $sid) -ErrorAction SilentlyContinue
    if ($null -eq $k) { return 'sem_perfil' }
    $perfil = [Environment]::ExpandEnvironmentVariables([string]$k.GetValue('ProfileImagePath'))
    if (-not $perfil.StartsWith($usuarios + '\', [StringComparison]::OrdinalIgnoreCase)) { return 'sem_perfil' }
    if ((Split-Path $perfil -Leaf) -match '^TEMP') { return 'sem_perfil' }
    if (-not (Test-Path -LiteralPath $perfil -PathType Container) -or (Eh-Reparse $perfil)) { return 'reparse' }
    return ''
}

$saida = @()
$n = 0
foreach ($sid in @($env:ITC_SIDS -split ',' | Where-Object { $_ })) {
    $n++
    $motivo = Recusa $sid
    if ($motivo) {
        $saida += @{ n = $n; categoria = ''; arquivos = 0; bytes = [int64]0; em_uso = 0; codigo = $motivo }
        continue
    }
    $perfil = [Environment]::ExpandEnvironmentVariables([string](Get-Item -LiteralPath ('HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\' + $sid)).GetValue('ProfileImagePath'))
    foreach ($cat in $CATEGORIAS.Keys) {
        $acc = @{ n = $n; categoria = $cat; arquivos = 0; bytes = [int64]0; em_uso = 0; codigo = '' }
        try {
            foreach ($rel in $CATEGORIAS[$cat]) {
                foreach ($raiz in @(Raizes $perfil $rel)) { Varrer $raiz $acc }
            }
        } catch {
            $acc.codigo = 'erro_' + $_.Exception.GetType().Name
        }
        $saida += $acc
    }
}
ConvertTo-Json -Compress -InputObject @($saida | ForEach-Object { [pscustomobject]$_ })

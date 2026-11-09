# Grava ou apaga os valores de um alvo (ADR-021). $env:ITC_HIVE; $env:ITC_OPERACOES =
# [{p, chave, nome, tipo, dado, acao, lista}], montado só do catálogo. Uma linha por operação.
Hive-Escrita $env:ITC_HIVE
# PS 5.1: ConvertFrom-Json devolve o array como um objeto só; ForEach-Object desenrola.
$ops = @($env:ITC_OPERACOES | ConvertFrom-Json | ForEach-Object { $_ })
foreach ($o in $ops) {
    if (-not (Raiz-Aceita $env:ITC_HIVE $o.chave)) { Falhar 'raiz' }
    if (-not (Valor-Aceito $o.chave $o.nome)) { Falhar 'valor' }
    if ($o.acao -notin @('gravar', 'apagar', 'apagar_se_igual', 'apagar_se_vazia')) { Falhar 'acao' }
    if ($o.tipo -notin @('dword', 'sz', 'expand_sz')) { Falhar 'tipo' }
    if ($PERFIL -ceq 'aparencia' -and $o.chave -eq $CHAVE_PAPEL -and $o.acao -eq 'gravar') {
        # Papel de parede (ADR-022): só o caminho que o Bench monta, e o estilo da lista fechada.
        # Nome: <sha>.<ext>, ou c<chave>.<sha>.<ext> sem SHA-256 no cadastro (ADR-028).
        if ($o.nome -eq 'WallpaperStyle' -and [string]$o.dado -cnotin @('0', '6', '10', '22')) { Falhar 'valor' }
        if ($o.nome -eq 'Wallpaper') {
            $pasta = [Environment]::GetFolderPath('CommonApplicationData') + '\ITC\Bench\papel\'
            if ([string]$o.dado -notmatch ('^' + [regex]::Escape($pasta) + '(c[0-9a-f]{64}\.)?[0-9a-f]{64}\.(jpg|jpeg|png)$')) { Falhar 'valor' }
            if (-not (Test-Path -LiteralPath ([string]$o.dado) -PathType Leaf)) { Falhar 'imagem' }
        }
    }
}
$base = Base $env:ITC_HIVE

function Abrir-Criando($base, [string]$chave) {
    $atual = $base
    $nova = $true
    foreach ($parte in $chave.Split('\')) {
        $k = $atual.OpenSubKey($parte, $true)
        if (-not $k) {
            if ($nova -and (Sob-Politica $chave)) {
                # Primeira chave que falta: ACL explícita, dono Administradores; as de baixo herdam.
                $sec = New-Object Security.AccessControl.RegistrySecurity
                $sec.SetSecurityDescriptorSddlForm($SDDL_NOVA)
                $k = $atual.CreateSubKey($parte, [Microsoft.Win32.RegistryKeyPermissionCheck]::ReadWriteSubTree, $sec)
                $nova = $false
            } else { $k = $atual.CreateSubKey($parte, $true) }
        }
        if ($atual -ne $base) { $atual.Close() }
        $atual = $k
    }
    return $atual
}

foreach ($o in $ops) {
    try {
        if ($o.acao -eq 'gravar') {
            $k = Abrir-Criando $base $o.chave
            if ($o.tipo -eq 'dword') { $k.SetValue($o.nome, [int]$o.dado, 'DWord') }
            elseif ($o.tipo -eq 'expand_sz') { $k.SetValue($o.nome, [string]$o.dado, 'ExpandString') }
            else { $k.SetValue($o.nome, [string]$o.dado, 'String') }
            $k.Close()
        } else {
            $k = $base.OpenSubKey($o.chave, $true)
            if ($k) {
                $atual = $k.GetValue($o.nome, $null, 'DoNotExpandEnvironmentNames')
                $apagar = $null -ne $atual
                if ($o.acao -eq 'apagar_se_igual') { $apagar = $apagar -and ("$atual" -ieq [string]$o.dado) }
                if ($o.acao -eq 'apagar_se_vazia') {
                    $lista = $base.OpenSubKey($o.lista, $false)
                    if ($lista) { $apagar = $apagar -and $lista.ValueCount -eq 0; $lista.Close() }
                }
                if ($apagar) { $k.DeleteValue($o.nome, $false) }
                $k.Close()
            }
        }
        Write-Output ('OK|' + $o.p)
    } catch {
        Write-Output ('ERRO|' + $_.Exception.GetType().Name + '|' + $o.p)
    }
}
$base.Close()

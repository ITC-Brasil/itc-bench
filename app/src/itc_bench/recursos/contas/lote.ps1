# ITC_LOTE = admin: contas locais ativas entram no grupo Administradores.
# ITC_LOTE = padrao: todas as contas locais saem dele, menos a Suporte e o nativo; a conta logada
# também sai (exceção do ADR-017, item 6). Recusa sem uma Suporte ativa e administradora.
$admins = Membros-Admin
$locais = @(Get-LocalUser | Where-Object { (Eh-Local $_) -and $_.SID.Value -notmatch '-(500|501|503|504)$' })
# As restritas fixas (Gestão, ADR-036) ficam fora do lote: nem viram admin nem perdem admin.
$locais = @($locais | Where-Object { -not ($RESTRITAS -contains $_.Name) })
if ($env:ITC_LOTE -eq 'padrao') {
    $suporte = @($locais | Where-Object { $PROTEGIDAS -contains $_.Name -and $_.Enabled -and $admins -contains $_.SID.Value })
    if ($suporte.Count -eq 0) { Falhar 'suporte_ausente' '' }
}
foreach ($c in $locais) {
    $ehAdmin = $admins -contains $c.SID.Value
    try {
        if ($env:ITC_LOTE -eq 'admin') {
            if ($c.Enabled -and -not $ehAdmin) { Garantir-Membro $SID_ADM $c; Write-Output ('MUDOU|' + $c.Name) }
        } elseif ($ehAdmin -and -not ($PROTEGIDAS -contains $c.Name)) {
            Garantir-Membro $SID_USR $c
            Remove-LocalGroupMember -SID $SID_ADM -Member $c
            Write-Output ('MUDOU|' + $c.Name)
        }
    } catch { Write-Output ('AVISO|' + $c.Name + '|' + ($_.Exception.Message -replace '[\r\n]+', ' ')) }
}
Write-Output 'OK'

param(
    [string]$cmd = "get_status",
    [string]$arg1 = "",
    [string]$arg2 = "",
    [string]$arg3 = "",
    [string]$arg4 = ""
)

$client = New-Object System.Net.Sockets.TcpClient
$client.Connect("127.0.0.1", 25001)
$stream = $client.GetStream()

$args = @{}
switch ($cmd) {
    "connect_mumu" { $args = @{path=$arg1; index=[int]$arg2; pkg=$arg3; app_index=[int]$arg4} }
    "set_apple_type" { $args = @{apple_type=$arg1} }
    "set_run_times" { $args = @{times=[int]$arg1} }
    "set_battle_type" { $args = @{battle_type=$arg1} }
    "load_config" { $args = @{filename=$arg1} }
    "popup_response" { $args = @{popup_id=$arg1; action=$arg2} }
    default { $args = @{} }
}

$packet = @{
    cmd = $cmd
    args = $args
}

$json = $packet | ConvertTo-Json -Compress
$data = [System.Text.Encoding]::UTF8.GetBytes($json)
$len = [BitConverter]::GetBytes([int]$data.Length)
[Array]::Reverse($len)

$stream.Write($len, 0, 4)
$stream.Write($data, 0, $data.Length)
$stream.Flush()

$buf = New-Object byte[] 4
$stream.Read($buf, 0, 4)
[Array]::Reverse($buf)
$msgLen = [BitConverter]::ToInt32($buf, 0)

$resp = New-Object byte[] $msgLen
$total = 0
while ($total -lt $msgLen) {
    $total += $stream.Read($resp, $total, $msgLen - $total)
}

$jsonStr = [System.Text.Encoding]::UTF8.GetString($resp)
$result = $jsonStr | ConvertFrom-Json
$result | ConvertTo-Json -Compress

$client.Close()

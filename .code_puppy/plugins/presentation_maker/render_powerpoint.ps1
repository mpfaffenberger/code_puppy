param(
    [Parameter(Mandatory = $true)][string]$InputPptx,
    [Parameter(Mandatory = $true)][string]$OutputPath
)

$powerPoint = $null
$presentation = $null

try {
    $powerPoint = New-Object -ComObject PowerPoint.Application
    $powerPoint.Visible = 1
    $presentation = $powerPoint.Presentations.Open($InputPptx, $true, $false, $false)
    # 18 is ppSaveAsPNG. PowerPoint exports one PNG per slide.
    $presentation.SaveAs($OutputPath, 18)
}
finally {
    if ($null -ne $presentation) {
        $presentation.Close()
    }
    if ($null -ne $powerPoint) {
        $powerPoint.Quit()
    }
}


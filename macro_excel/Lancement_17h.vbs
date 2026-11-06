' Lance l'envoi TIS Belges (appelé par la tâche planifiée de 17h).
' Ouvre TIS_Belges.xlsm (même dossier) en arrière-plan, exécute LancementAuto, enregistre le journal.
Option Explicit
Dim fso, dossier, xl, wb
Set fso = CreateObject("Scripting.FileSystemObject")
dossier = fso.GetParentFolderName(WScript.ScriptFullName)
Set xl = CreateObject("Excel.Application")
xl.Visible = False
xl.DisplayAlerts = False
On Error Resume Next
Set wb = xl.Workbooks.Open(dossier & "\TIS_Belges.xlsm")
If Not wb Is Nothing Then
    xl.Run "'" & wb.Name & "'!LancementAuto"
    wb.Close True
End If
xl.Quit

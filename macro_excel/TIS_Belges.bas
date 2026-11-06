Attribute VB_Name = "TIS_Belges"
Option Explicit

' =============================================================================
'  TIS Belges : actualisation, contrôles, archivage, historique Valor, envoi Six
'  Boutons de l'onglet Pilotage : EnvoyerASix, EssaiSansEnvoi, VerifierPoste
'  Tâche de 17h : LancementAuto (via Lancement_17h.vbs)
'  Règle : si un contrôle échoue, rien n'est envoyé à Six.
' =============================================================================

' ---- Réglages -----------------------------------------------------------------
Private Const DOSSIER_RELATIF As String = "\Rothschild & Co\AM-DATATEAM-INT - Documents\A - Data Vendors\1. DATABASES\2. BASES DE DONNEES GLOBALES\Six Financial Information\3. TIS Belges"
Private Const FICHIER_MAITRE As String = "TISBE_PROD.xlsx"
Private Const FICHIER_FINAL As String = "TISBE_Rothschild & Co AM_File.xlsx"
Private Const HISTORIQUE As String = "Historique TIS Belges\TIS BE_R-co Valor.xlsx"
Private Const ONGLET_HISTO As String = "Sheet2"
Private Const ONGLET_PARAM As String = "Paramètres"
Private Const ONGLET_DONNEES As String = "TIS BE"
Private Const NOM_VALOR As String = "R-co Valor"
Private Const DSN As String = "RMMPRD"

Private Const EXPEDITEUR As String = "AMEUDataTeam@rmm-co.com"
Private Const DESTINATAIRES As String = "notification.fr@six-financial-information.com; notification.benelux@six-financial-information.com"
Private Const OBJET As String = "TIS BELGES"
Private Const OPERATEUR As String = "noa.robin@rothschildandco.com"   ' essais et alertes

Private Const LIGNES_MIN As Long = 150
Private Const LIGNES_MAX As Long = 400
Private Const HEURE_LIMITE As String = "18:00"    ' reprises automatiques jusqu'à cette heure
Private Const ATTENTE_MIN As Long = 15            ' minutes entre deux reprises

Private Const ONGLET_PILOTAGE As String = "Pilotage"
Private Const LIGNE_JOURNAL As Long = 9           ' première ligne du journal (la plus récente)

Private gReessayable As Boolean
Private gDerniereErreur As String

' ---- Boutons -------------------------------------------------------------------

Public Sub EnvoyerASix()
    If MsgBox("Envoyer les TIS Belges à Six maintenant ?" & vbCrLf & vbCrLf & _
              "Le fichier sera actualisé, contrôlé, archivé puis envoyé." & vbCrLf & _
              "Rien ne part si un contrôle échoue.", vbQuestion + vbOKCancel, "TIS Belges") <> vbOK Then Exit Sub
    Executer False, True
End Sub

Public Sub EssaiSansEnvoi()
    Executer True, True
End Sub

' Appelé par la tâche planifiée : pas de fenêtre, reprises jusqu'à HEURE_LIMITE, alerte en cas d'échec.
Public Sub LancementAuto()
    Dim limite As Date
    limite = Date + TimeValue(HEURE_LIMITE)
    Do
        If Executer(False, False) Then Exit Sub
        If Not gReessayable Or Now + TimeSerial(0, ATTENTE_MIN, 0) > limite Then Exit Do
        Application.Wait Now + TimeSerial(0, ATTENTE_MIN, 0)
    Loop
    On Error Resume Next
    EnvoyerMail OPERATEUR, "[TIS Belges] Échec du " & Format(Date, "dd/mm/yyyy"), _
                "L'envoi automatique n'a pas abouti. Rien n'a été envoyé à Six." & vbCrLf & vbCrLf & gDerniereErreur
End Sub

' ---- Déroulé -------------------------------------------------------------------

Private Function Executer(ByVal essai As Boolean, ByVal interactif As Boolean) As Boolean
    Dim mode As String, cle As String, etape As String
    Dim base As String, sortie As String, archive As String, fichierFinal As String, histo As String, travail As String
    Dim wbTravail As Workbook, wbHisto As Workbook
    Dim lignes As Collection, erreurs As String, v As Variant

    mode = IIf(essai, "Essai", "Réel")
    cle = Format(Date, "yyyymmdd")
    gReessayable = False
    etape = "Démarrage"

    If Weekday(Date, vbMonday) > 5 Then
        Journal mode, etape, "Ignoré", "Jour non ouvré"
        Executer = True
        Exit Function
    End If
    If Not essai And DejaEnvoye(cle) Then
        Journal mode, etape, "Ignoré", "Déjà envoyé aujourd'hui"
        If interactif Then MsgBox "Les TIS Belges du jour ont déjà été envoyés.", vbInformation, "TIS Belges"
        Executer = True
        Exit Function
    End If

    On Error GoTo Echec
    Application.ScreenUpdating = False
    Application.DisplayAlerts = False
    Application.StatusBar = "TIS Belges : " & mode & " en cours..."

    ' -- Dossiers
    etape = "Dossiers"
    base = Dossier()
    If Dir(base & "\" & FICHIER_MAITRE) = "" Then Err.Raise vbObjectError + 1, , "Fichier maître introuvable : " & base & "\" & FICHIER_MAITRE
    histo = base & "\" & HISTORIQUE
    If Dir(histo) = "" Then Err.Raise vbObjectError + 1, , "Historique Valor introuvable : " & histo
    If essai Then
        sortie = Environ("TEMP") & "\TIS_Belges_essai"
        CreerDossier sortie & "\Historique TIS Belges"
        If Dir(sortie & "\" & HISTORIQUE) = "" Then FileCopy histo, sortie & "\" & HISTORIQUE
        histo = sortie & "\" & HISTORIQUE
    Else
        sortie = base
    End If
    CreerDossier sortie & "\" & Year(Date)
    archive = sortie & "\" & Year(Date) & "\TISBE_PROD_" & cle & ".xlsx"
    fichierFinal = sortie & "\" & FICHIER_FINAL

    ' -- Actualisation (copie du maître : l'original n'est jamais modifié)
    etape = "Actualisation"
    travail = Environ("TEMP") & "\TISBE_travail_" & cle & ".xlsx"
    If Dir(travail) <> "" Then Kill travail
    FileCopy base & "\" & FICHIER_MAITRE, travail
    Set wbTravail = Workbooks.Open(travail, UpdateLinks:=0)
    With wbTravail.Worksheets(ONGLET_PARAM).Range("E4")
        .NumberFormat = "@"
        .Value = cle
    End With
    RendreSynchrone wbTravail
    gReessayable = True
    wbTravail.RefreshAll
    Application.CalculateUntilAsyncQueriesDone
    Journal mode, etape, "OK", ""

    ' -- Contrôles bloquants
    etape = "Contrôle"
    Set lignes = LireDonnees(wbTravail.Worksheets(ONGLET_DONNEES))
    erreurs = Controler(lignes, cle)
    If erreurs <> "" Then Err.Raise vbObjectError + 2, , erreurs
    gReessayable = False
    Journal mode, etape, "OK", lignes.Count & " lignes"

    ' -- Archive (avec l'onglet Paramètres)
    etape = "Archivage"
    If Dir(archive) <> "" Then
        If essai Then
            Kill archive
        Else
            Err.Raise vbObjectError + 3, , "Archive déjà présente : " & archive & " (vérification manuelle)."
        End If
    End If
    wbTravail.SaveCopyAs archive
    Journal mode, etape, "OK", archive

    ' -- Historique R-co Valor
    etape = "Historique Valor"
    Set wbHisto = Workbooks.Open(histo, UpdateLinks:=0)
    Journal mode, etape, "OK", AjouterValor(wbHisto.Worksheets(ONGLET_HISTO), lignes, cle)
    wbHisto.Close SaveChanges:=True
    Set wbHisto = Nothing

    ' -- Fichier final (sans l'onglet Paramètres)
    etape = "Fichier final"
    wbTravail.Worksheets(ONGLET_PARAM).Delete
    If Dir(fichierFinal) <> "" Then Kill fichierFinal
    wbTravail.SaveAs fichierFinal, xlOpenXMLWorkbook
    wbTravail.Close SaveChanges:=False
    Set wbTravail = Nothing
    Journal mode, etape, "OK", fichierFinal

    ' -- Envoi
    etape = "Envoi"
    If essai Then
        EnvoyerMail OPERATEUR, "[TEST] " & OBJET, CorpsMail(), fichierFinal
        Journal mode, etape, "OK", "Mail de test envoyé à " & OPERATEUR
    Else
        EnvoyerMail DESTINATAIRES, OBJET, CorpsMail(), fichierFinal
        Journal mode, etape, "OK", "Envoyé à Six"
        ThisWorkbook.Save   ' le journal garde la trace de l'envoi : pas de double envoi
    End If

    Executer = True
    If interactif Then
        MsgBox IIf(essai, "Essai réussi. Le mail de test est parti vers " & OPERATEUR & "." & vbCrLf & "Fichiers : " & sortie, _
                          "Envoyé à Six."), vbInformation, "TIS Belges"
    End If

Fin:
    On Error Resume Next
    If Not wbTravail Is Nothing Then wbTravail.Close SaveChanges:=False
    If Not wbHisto Is Nothing Then wbHisto.Close SaveChanges:=False
    If travail <> "" Then If Dir(travail) <> "" Then Kill travail
    Application.DisplayAlerts = True
    Application.ScreenUpdating = True
    Application.StatusBar = False
    Exit Function

Echec:
    gDerniereErreur = "Étape « " & etape & " » : " & Err.Description
    Journal mode, etape, "ÉCHEC", Err.Description
    If interactif Then
        MsgBox "Échec à l'étape « " & etape & " »." & vbCrLf & vbCrLf & Err.Description & vbCrLf & vbCrLf & _
               IIf(etape = "Envoi", "Vérifiez les éléments envoyés avant de relancer.", "Rien n'a été envoyé à Six."), _
               vbExclamation, "TIS Belges"
    End If
    Resume Fin
End Function

' ---- Étapes ---------------------------------------------------------------------

Private Sub RendreSynchrone(ByVal wb As Workbook)
    Dim c As WorkbookConnection
    On Error Resume Next
    For Each c In wb.Connections
        c.OLEDBConnection.BackgroundQuery = False
        c.ODBCConnection.BackgroundQuery = False
    Next c
    On Error GoTo 0
End Sub

' Lignes de données (colonnes A à H) sous l'en-tête « ISIN ».
Private Function LireDonnees(ByVal ws As Worksheet) As Collection
    Dim r As Long, entete As Long, j As Long, ligne(1 To 8) As Variant
    Set LireDonnees = New Collection
    For r = 1 To 20
        If Trim(CStr(ws.Cells(r, 1).Value)) = "ISIN" Then entete = r: Exit For
    Next r
    If entete = 0 Then Err.Raise vbObjectError + 2, , "En-tête « ISIN » introuvable dans l'onglet " & ws.Name & "."
    r = entete + 1
    Do While Trim(CStr(ws.Cells(r, 1).Value)) <> ""
        For j = 1 To 8
            ligne(j) = ws.Cells(r, j).Value
        Next j
        LireDonnees.Add ligne
        r = r + 1
    Loop
End Function

Private Function Controler(ByVal lignes As Collection, ByVal cle As String) As String
    Dim v As Variant, k As String, j As Long, msg As String
    Dim dates As Long, isin As Long, montant As Long, typ As Long, doublons As Long, nom As Long
    Dim vus As Object
    Set vus = CreateObject("Scripting.Dictionary")

    If lignes.Count = 0 Then
        Controler = "Aucune ligne : la requête n'a rien renvoyé (données pas encore publiées ?)."
        Exit Function
    End If
    If lignes.Count < LIGNES_MIN Or lignes.Count > LIGNES_MAX Then
        msg = msg & "Nombre de lignes " & lignes.Count & " hors de la plage " & LIGNES_MIN & "-" & LIGNES_MAX & ". "
    End If
    For Each v In lignes
        If DateTexte(v(4)) <> cle Then dates = dates + 1
        If Len(Trim(CStr(v(1)))) <> 12 Then isin = isin + 1
        If Trim(CStr(v(2))) = "" Then nom = nom + 1
        If Not EstNombre(v(7)) Then montant = montant + 1
        If v(8) <> "TIBR" And v(8) <> "TISF" Then typ = typ + 1
        k = ""
        For j = 1 To 8
            k = k & CStr(v(j)) & "|"
        Next j
        If vus.Exists(k) Then doublons = doublons + 1 Else vus.Add k, True
    Next v
    If dates > 0 Then msg = msg & dates & " ligne(s) non datée(s) du " & cle & " (données pas encore publiées ?). "
    If isin > 0 Then msg = msg & isin & " ISIN invalide(s). "
    If nom > 0 Then msg = msg & nom & " nom(s) de fonds vide(s). "
    If montant > 0 Then msg = msg & montant & " montant(s) TIS non numérique(s). "
    If typ > 0 Then msg = msg & typ & " type(s) de fiscalité inattendu(s). "
    If doublons > 0 Then msg = msg & doublons & " ligne(s) en double. "
    Controler = Trim(msg)
End Function

Private Function AjouterValor(ByVal ws As Worksheet, ByVal lignes As Collection, ByVal cle As String) As String
    Dim v As Variant, attendu As Long, deja As Long, derniere As Long, n As Long, valeurs As Variant, r As Long

    For Each v In lignes
        If Trim(CStr(v(2))) = NOM_VALOR Then attendu = attendu + 1
    Next v
    If attendu = 0 Then Err.Raise vbObjectError + 4, , "Aucune ligne « " & NOM_VALOR & " » dans le fichier."

    derniere = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row
    If derniere > 1 Then
        valeurs = ws.Range("D1:D" & derniere).Value
        For r = 1 To UBound(valeurs, 1)
            If DateTexte(valeurs(r, 1)) = cle Then deja = deja + 1
        Next r
    End If

    If deja = attendu Then
        AjouterValor = "Déjà à jour (" & deja & " lignes)"
        Exit Function
    End If
    If deja > 0 Then Err.Raise vbObjectError + 4, , deja & " lignes déjà présentes pour " & cle & ", " & attendu & " attendues : vérification manuelle."

    For Each v In lignes
        If Trim(CStr(v(2))) = NOM_VALOR Then
            n = n + 1
            ws.Cells(derniere + n, 1).Resize(1, 8).Value = Array(v(1), v(2), v(3), CLng(cle), Empty, v(6), v(7), v(8))
        End If
    Next v
    AjouterValor = n & " lignes ajoutées"
End Function

Private Sub EnvoyerMail(ByVal a As String, ByVal sujet As String, ByVal corps As String, Optional ByVal pieceJointe As String = "")
    Dim ol As Object, m As Object, i As Long, trouve As Boolean
    Set ol = CreateObject("Outlook.Application")
    Set m = ol.CreateItem(0)
    For i = 1 To ol.Session.Accounts.Count
        If LCase(ol.Session.Accounts.Item(i).SmtpAddress) = LCase(EXPEDITEUR) Then
            Set m.SendUsingAccount = ol.Session.Accounts.Item(i)
            trouve = True
        End If
    Next i
    If Not trouve Then m.SentOnBehalfOfName = EXPEDITEUR
    m.To = a
    m.Subject = sujet
    m.Body = corps
    If pieceJointe <> "" Then m.Attachments.Add pieceJointe
    m.Send
End Sub

Private Function CorpsMail() As String
    CorpsMail = "Bonjour," & vbCrLf & vbCrLf & "Vous trouverez ci-joint les TIS belges." & vbCrLf & vbCrLf & "Cordialement"
End Function

' ---- Contrôle du poste --------------------------------------------------------

Public Sub VerifierPoste()
    Dim base As String, rapport As String, ol As Object

    base = Dossier()
    rapport = Ligne(Dir(base & "\" & FICHIER_MAITRE) <> "", "Fichier maître", base & "\" & FICHIER_MAITRE)
    rapport = rapport & Ligne(Dir(base & "\" & HISTORIQUE) <> "", "Historique Valor", HISTORIQUE)
    rapport = rapport & Ligne(DsnExiste(), "Source ODBC « " & DSN & " »", "à créer dans odbcad32 si absente")

    On Error Resume Next
    Set ol = CreateObject("Outlook.Application")
    On Error GoTo 0
    rapport = rapport & Ligne(Not ol Is Nothing, "Outlook", "")
    rapport = rapport & Ligne(TacheExiste(), "Envoi automatique de 17h", "lancer Programmer_17h.bat pour l'activer")

    MsgBox rapport, vbInformation, "TIS Belges : contrôle du poste"
End Sub

Private Function Ligne(ByVal ok As Boolean, ByVal libelle As String, ByVal detail As String) As String
    Ligne = IIf(ok, "[OK]      ", "[À FAIRE] ") & libelle & IIf(ok Or detail = "", "", " : " & detail) & vbCrLf
End Function

Private Function DsnExiste() As Boolean
    Dim sh As Object, cles As Variant, k As Variant
    Set sh = CreateObject("WScript.Shell")
    cles = Array("HKCU\Software\ODBC\ODBC.INI\" & DSN & "\", "HKLM\Software\ODBC\ODBC.INI\" & DSN & "\", _
                 "HKLM\Software\WOW6432Node\ODBC\ODBC.INI\" & DSN & "\")
    On Error Resume Next
    For Each k In cles
        Err.Clear
        sh.RegRead k
        If Err.Number = 0 Then DsnExiste = True: Exit Function
    Next k
End Function

Private Function TacheExiste() As Boolean
    TacheExiste = (CreateObject("WScript.Shell").Run("schtasks /Query /TN ""TIS Belges - envoi quotidien""", 0, True) = 0)
End Function

' ---- Onglet Pilotage et journal -----------------------------------------------

' À lancer une fois après l'import du module : crée l'onglet Pilotage et ses boutons.
Public Sub InstallerPilotage()
    Dim ws As Worksheet
    On Error Resume Next
    Set ws = ThisWorkbook.Worksheets(ONGLET_PILOTAGE)
    On Error GoTo 0
    If ws Is Nothing Then
        Set ws = ThisWorkbook.Worksheets.Add(Before:=ThisWorkbook.Sheets(1))
        ws.Name = ONGLET_PILOTAGE
    End If
    Do While ws.Shapes.Count > 0
        ws.Shapes(1).Delete
    Loop

    ActiveWindow.DisplayGridlines = False
    With ws
        .Range("A1").Value = "TIS BELGES"
        .Range("A1").Font.Size = 22
        .Range("A1").Font.Bold = True
        .Range("A2").Value = "Envoi quotidien à Six Financial Information · Data Team"
        .Range("A4").Value = "Dossier TIS Belges (vide = automatique) :"
        .Range("A4").Font.Bold = True
        .Range("B5").Value = "Dossier utilisé : " & Environ("USERPROFILE") & DOSSIER_RELATIF
        .Range("B5").Font.Italic = True
        .Range("A8:F8").Value = Array("Date", "Heure", "Mode", "Étape", "Statut", "Détail")
        .Range("A8:F8").Font.Bold = True
        .Range("A8:F8").Interior.Color = RGB(0, 0, 0)
        .Range("A8:F8").Font.Color = RGB(255, 255, 255)
        .Columns("A").ColumnWidth = 12
        .Columns("B").ColumnWidth = 10
        .Columns("C").ColumnWidth = 8
        .Columns("D").ColumnWidth = 18
        .Columns("E").ColumnWidth = 10
        .Columns("F").ColumnWidth = 90
    End With

    AjouterBouton ws, "ENVOYER À SIX", "EnvoyerASix", 330, 10, RGB(255, 255, 0)
    AjouterBouton ws, "ESSAI SANS ENVOI", "EssaiSansEnvoi", 500, 10, RGB(255, 255, 255)
    AjouterBouton ws, "VÉRIFIER LE POSTE", "VerifierPoste", 670, 10, RGB(255, 255, 255)
    ws.Activate
End Sub

Private Sub AjouterBouton(ByVal ws As Worksheet, ByVal texte As String, ByVal macro As String, _
                          ByVal gauche As Single, ByVal haut As Single, ByVal couleur As Long)
    With ws.Shapes.AddShape(1, gauche, haut, 160, 40)
        .Fill.ForeColor.RGB = couleur
        .Line.ForeColor.RGB = RGB(0, 0, 0)
        .Line.Weight = 2.5
        .TextFrame2.TextRange.Text = texte
        .TextFrame2.TextRange.Font.Bold = True
        .TextFrame2.TextRange.Font.Size = 11
        .TextFrame2.TextRange.Font.Fill.ForeColor.RGB = RGB(0, 0, 0)
        .TextFrame2.TextRange.ParagraphFormat.Alignment = 2
        .TextFrame2.VerticalAnchor = 3
        .OnAction = macro
    End With
End Sub

Private Function Dossier() As String
    Dim choisi As String
    On Error Resume Next
    choisi = Trim(CStr(ThisWorkbook.Worksheets(ONGLET_PILOTAGE).Range("B4").Value))
    On Error GoTo 0
    If choisi <> "" Then
        Dossier = choisi
    Else
        Dossier = Environ("USERPROFILE") & DOSSIER_RELATIF
    End If
    If Right(Dossier, 1) = "\" Then Dossier = Left(Dossier, Len(Dossier) - 1)
End Function

Private Sub Journal(ByVal mode As String, ByVal etape As String, ByVal statut As String, ByVal detail As String)
    Dim ws As Worksheet
    On Error Resume Next
    Set ws = ThisWorkbook.Worksheets(ONGLET_PILOTAGE)
    If ws Is Nothing Then Exit Sub
    ws.Rows(LIGNE_JOURNAL).Insert
    ws.Cells(LIGNE_JOURNAL, 1).Resize(1, 6).Value = Array(Format(Date, "dd/mm/yyyy"), Format(Time, "hh:nn:ss"), mode, etape, statut, detail)
    ws.Cells(LIGNE_JOURNAL, 1).Resize(1, 6).Interior.Color = Choose( _
        IIf(statut = "OK", 1, IIf(statut = "ÉCHEC", 2, 3)), RGB(220, 235, 255), RGB(255, 120, 120), RGB(255, 255, 255))
    ws.Cells(LIGNE_JOURNAL, 1).Resize(1, 6).Font.Color = RGB(0, 0, 0)
    ws.Cells(LIGNE_JOURNAL, 1).Resize(1, 6).Font.Bold = (statut = "ÉCHEC")
    DoEvents
End Sub

Private Function DejaEnvoye(ByVal cle As String) As Boolean
    Dim ws As Worksheet, r As Long, aujourdhui As String
    On Error Resume Next
    Set ws = ThisWorkbook.Worksheets(ONGLET_PILOTAGE)
    If ws Is Nothing Then Exit Function
    aujourdhui = Format(Date, "dd/mm/yyyy")
    r = LIGNE_JOURNAL
    Do While ws.Cells(r, 1).Value <> ""
        If CStr(ws.Cells(r, 1).Text) = aujourdhui And ws.Cells(r, 3).Value = "Réel" _
           And ws.Cells(r, 4).Value = "Envoi" And ws.Cells(r, 5).Value = "OK" Then
            DejaEnvoye = True
            Exit Function
        End If
        r = r + 1
    Loop
End Function

' ---- Utilitaires ----------------------------------------------------------------

Private Function DateTexte(ByVal v As Variant) As String
    If IsNumeric(v) And VarType(v) <> vbString Then
        DateTexte = CStr(CLng(v))
    Else
        DateTexte = Trim(CStr(v))
    End If
End Function

Private Function EstNombre(ByVal v As Variant) As Boolean
    Select Case VarType(v)
        Case vbDouble, vbSingle, vbLong, vbInteger, vbCurrency, vbDecimal
            EstNombre = True
    End Select
End Function

Private Sub CreerDossier(ByVal chemin As String)
    Dim parties() As String, i As Long, courant As String
    parties = Split(chemin, "\")
    courant = parties(0)
    For i = 1 To UBound(parties)
        courant = courant & "\" & parties(i)
        If Dir(courant, vbDirectory) = "" Then MkDir courant
    Next i
End Sub

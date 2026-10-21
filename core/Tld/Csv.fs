module Tld.Csv

// Reading an uploaded CSV, as Python's csv.DictReader reads it: comma
// separated, double quotes around fields that hold commas, quotes or line
// breaks, "" for a quote inside one, any of \r\n, \n or \r between rows. A
// quote in the middle of an unquoted field is just a character. Blank lines
// are skipped. Shared, so any upload the site takes later reads the same way.
//
// The shell decodes the bytes (UTF-8, byte order mark dropped, bad bytes
// replaced) and hands over the text.

open Fable.Core.JsInterop

// Every row as a list of fields, in file order
let rows (text: string) : string array array =
    let text = if isNull text then "" elif text.StartsWith "﻿" then text.Substring 1 else text
    let rows = ResizeArray<string array>()
    let row = ResizeArray<string>()
    let field = System.Text.StringBuilder()
    let mutable inQuotes = false
    let mutable fieldStarted = false // the current field has a character or an opening quote
    let mutable i = 0

    let endField () =
        row.Add(field.ToString())
        field.Clear() |> ignore
        fieldStarted <- false

    // a line with nothing on it gives no fields, and DictReader skips it; a line holding "" is a row
    let endRow () =
        if fieldStarted || row.Count > 0 then endField ()
        if row.Count > 0 then rows.Add(row.ToArray())
        row.Clear()

    while i < text.Length do
        let c = text.[i]
        if inQuotes then
            if c = '"' then
                if i + 1 < text.Length && text.[i + 1] = '"' then
                    field.Append('"') |> ignore
                    i <- i + 1
                else
                    inQuotes <- false
            else
                field.Append(c) |> ignore
        else
            match c with
            | '"' when not fieldStarted ->
                inQuotes <- true
                fieldStarted <- true
            | ',' -> endField ()
            | '\r' ->
                endRow ()
                if i + 1 < text.Length && text.[i + 1] = '\n' then i <- i + 1
            | '\n' -> endRow ()
            | _ ->
                field.Append(c) |> ignore
                fieldStarted <- true
        i <- i + 1

    endRow ()
    rows.ToArray()

(*
 The first row is the header, every other row an object keyed by it. A short
 row leaves its missing columns null; a long row's extra fields are dropped. A
 header named twice keeps the later column, as dict(zip()) does.
*)
let read (text: string) =
    let all = rows text
    if Array.isEmpty all then {| header = [||]; records = [||] |}
    else
        let header = all.[0]
        let records =
            all.[1..]
            |> Array.map (fun r ->
                createObj (header |> Array.mapi (fun i h -> h, (if i < r.Length then box r.[i] else null))))
        {| header = header; records = records |}

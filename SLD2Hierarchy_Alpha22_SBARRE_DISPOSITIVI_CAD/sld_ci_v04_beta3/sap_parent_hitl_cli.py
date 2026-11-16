"""Explicit operator-confirmed conversion of Alpha11 suggested groups to Alpha10 HITL JSON."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .sap.parentage_alpha11 import build_explicit_review


def main():
    p=argparse.ArgumentParser(description='Alpha11 explicit HITL: inspect each proposed TR/inverter group')
    p.add_argument('--proposals-json',required=True)
    p.add_argument('--out',required=True)
    args=p.parse_args()
    prop=json.loads(Path(args.proposals_json).read_text(encoding='utf-8-sig'))
    print('IMPIANTO:',prop.get('plant_id',''))
    print('Le relazioni proposte NON sono connessioni elettriche dimostrate.')
    print('Approva solo dopo controllo del documento e delle CU esplicitamente indicate.')
    selections=[]
    for i,g in enumerate(prop.get('suggested_hitl_groups',[]),1):
        print('\nGruppo',i,'TR',g['transformer_slot'],'-> inverter',g['inverter_slots'])
        print('CU interessate:',g['cu_ids'])
        if g.get('printed_label_conflict_present'):
            print('ATTENZIONE: almeno una etichetta inverter non e coerente con il numero della CU.')
        try:
            choice=input('CONFERMO il gruppo dopo verifica (digitare CONFERMO / INVIO per saltare): ').strip()
        except EOFError:
            p.exit(2,'ERRORE: conferma interattiva non disponibile.\n')
        if choice!='CONFERMO':
            print('Gruppo non approvato.');continue
        ev=input('Riferimento della verifica manuale (obbligatorio, es. PV11:p1:CU 1-18...): ').strip()
        if not ev:
            print('Nessuna evidenza: gruppo NON approvato.');continue
        selections.append((i,ev))
    review=build_explicit_review(prop,selections)
    out=Path(args.out)
    if out.exists():
        p.exit(2,'ERRORE: file HITL gia esistente, non sovrascritto: '+str(out)+'\n')
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(review,indent=2,ensure_ascii=False),encoding='utf-8')
    print('Gruppi esplicitamente confermati:',len(review['confirmed_tr_inverter_groups']))
    print('Review operatore:',out)
    return 0

if __name__=='__main__':raise SystemExit(main())

"""Fictional CSV reproduction helper; never imports or connects to a database."""
import argparse,csv
from pathlib import Path
from uuid import UUID
p=argparse.ArgumentParser();p.add_argument('destination',type=Path);p.add_argument('--location-id',type=UUID,required=True);p.add_argument('--cutoff',required=True);p.add_argument('--sku',default='DEMO-BARE');args=p.parse_args()
from datetime import date
date.fromisoformat(args.cutoff)
with args.destination.open('x',newline='') as f:
    writer=csv.writer(f);writer.writerow(['external_id','sku','location_id','state','ownership','quantity','serial','batch','unit_cost','cost_status','currency','opening_date','basis'])
    writer.writerow(['OPEN-008',args.sku,str(args.location_id),'qualified','own',2,'','FICTIONAL-OPEN','20.00','confirmed','CNY',args.cutoff,'虚构期初依据'])

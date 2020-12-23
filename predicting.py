import datetime, os, configparser, pickle, pytz, json

import pandas as pd
import numpy as np

from argparse import ArgumentParser
from elasticsearch import Elasticsearch, helpers


class Main():
  def __init__(self):
    config = configparser.ConfigParser()
    config.read(os.path.dirname(os.path.abspath(__file__))+"/config.ini")
    self.now = datetime.datetime.now(pytz.timezone("Asia/Taipei"))
    self.preds = eval(config.get("Train", "preds"))
    self.K = eval(config.get("Train", "K"))
    self.N_Class = eval(config.get("Train", "N_Class"))
    self.label_table = eval(config.get("Train", "label_table"))
    self.model_path = os.path.dirname(os.path.abspath(__file__))+"/"+config.get("Train", "model_path")
    self.label_msg = eval(config.get("Output", "label_msg"))
    self.proto_table = eval(config.get("Output", "proto_table"))
    self.sig_id = eval(config.get("Output", "sig_id"))
  
  def predict(self, df):
    df = df.copy()
    with open(self.model_path+"preds_sel.txt","r") as text_file:
      preds = eval(text_file.read())
    df = df[preds]
    fs = [f for f in os.listdir(self.model_path) if ".model.pickle.dat" in f]
    predictions = np.zeros([self.K, len(df), self.N_Class])
    for i, f in enumerate(fs):
      m_path = os.path.join(self.model_path, f)
      m = pickle.load(open(m_path, "rb"))
      predictions[i] = m.predict_proba(df.values)
    pred = np.argmax(predictions.mean(axis=0), axis=1)
    pred = [self.label_table[x] for x in pred]
    return pred

  def toJSON(self, pred, df):
    df = pd.DataFrame(df)
    df["title"] = pred
    df["Protocol"] = df["Protocol"].apply(lambda x: self.proto_table[x])
    df.rename(columns={"Src IP":"src_ip", "Src Port":"src_port", "Dst IP":"dest_ip", "Dst Port":"dest_port", "Protocol":"proto"}, inplace=True)
    df["timestamp"] = self.now.strftime("%Y-%m-%dT%H:%M:%S.%f+08:00")
    df["ingest_timestamp"] = (self.now - datetime.timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    df["reference"] = "0"
    df["module"] = "ETA"
    df["log_type"] = "traffic"
    df["dump_status"] = "0"
    df["event_type"] = "alert"
    df["severity"] = 2
    df["message"] = df["title"].apply(lambda x: self.label_msg[x])
    df["action"] = "0"
    df["rule_sig_id"] = df["title"].apply(lambda x: self.sig_id[x])
    df["alert_group_id"] = 0
    df["alert"] = df.apply(lambda x: {"category":x["title"], "severity":x["severity"], "signature":x["message"],
                                      "action":x["action"], "signature_id":x["rule_sig_id"], "gid":x["alert_group_id"]}, axis=1)
    df = df[df["title"] != "normal"]
    df.drop(["title", "severity", "message", "action", "rule_sig_id", "alert_group_id"], axis=1, inplace=True)
    output = eval(df.to_json(orient="records"))
    with open(os.path.dirname(os.path.abspath(__file__))+"/output-{}.json".format(datetime.datetime.now(pytz.timezone("Asia/Taipei")).strftime("%Y-%m-%dT%H:%M:%S")), "w") as f:
      f.write(json.dumps(output, ensure_ascii=False))
      f.close()

if __name__ == "__main__":
  load_main = Main()
  parser = ArgumentParser()
  parser.add_argument("-f", help="filepath", dest="filepath")
  args = parser.parse_args()
  df = pd.read_csv(args.filepath)
  if "Src IP" not in df.columns:
    df["Src IP"] = "NA"
  if "Dst IP" not in df.columns:
    df["Dst IP"] = "NA"
  pred = load_main.predict(df)
  output = load_main.toJSON(pred, df[["id","Protocol","Dst Port","Src Port","Src IP","Dst IP"]])
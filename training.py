import datetime, os, configparser, pickle, pytz, shutil

import pandas as pd
import numpy as np

from elasticsearch import Elasticsearch, helpers
from xgboost.sklearn import XGBClassifier
from sklearn.model_selection import GridSearchCV, StratifiedKFold
from argparse import ArgumentParser


class Main():
  def __init__(self):
    config = configparser.ConfigParser()
    config.read(os.path.dirname(os.path.abspath(__file__))+"/config.ini")
    self.now = datetime.datetime.now(pytz.timezone("Asia/Taipei"))
    self.preds = eval(config.get("Train", "preds"))
    self.K = eval(config.get("Train", "K"))
    self.skfold = StratifiedKFold(n_splits=self.K, random_state=7, shuffle=True)
    self.N_Class = eval(config.get("Train", "N_Class"))
    self.label_table = eval(config.get("Train", "label_table"))
    self.model_path = os.path.dirname(os.path.abspath(__file__))+"/"+config.get("Train", "model_path")
  
  def processData(self, df):
    df = df.copy()
    def mapping(m):
      encode = int()
      for k, v in self.label_table.items():
        if m == v:
          encode = k
          break
      return encode
    y = df["class"].apply(mapping).values
    df.drop(["class", "id"], axis=1, inplace=True)
    df.replace(np.inf, 1E6, inplace=True)
    df.fillna(0, inplace=True) 
    return df, y

  def paraGridSearch(self, X, y):
    X = X.copy()
    parameters = {"nthread":[4],
                  "objective":["multi:softmax"],
                  "learning_rate": [0.001, 0.01, 0.05],
                  "max_depth": [2, 5, 7],
                  "min_child_weight": [3],
                  "gamma": [0.1],
                  "subsample": [0.8],
                  "colsample_bytree": [0.7],
                  "n_estimators": [100, 300, 500, 700, 900, 1100],
                  "seed": [1337]}
    xgb_model = XGBClassifier()
    clf = GridSearchCV(xgb_model, parameters, n_jobs=5, cv=self.skfold, scoring="f1_micro", verbose=1, refit=True)
    clf.fit(X.values, y)
    best_params = clf.best_params_
    return best_params

  def initialEnv(self):
    if os.path.exists(self.model_path):
      try:
        shutil.rmtree(os.path.dirname(os.path.abspath(__file__))+"/previous_model/")
      except:
        pass
      os.rename(self.model_path, os.path.dirname(os.path.abspath(__file__))+"/previous_model/")
    os.mkdir(self.model_path)
    np.random.seed(1314)

  def model(self, best_params, X, y, fmp=False, save=False):
    clf_best = XGBClassifier(learning_rate=best_params["learning_rate"],\
                             n_estimators=best_params["n_estimators"],\
                             max_depth=best_params["max_depth"],\
                             min_child_weight=best_params["min_child_weight"],\
                             gamma=best_params["gamma"],\
                             subsample=best_params["subsample"],\
                             colsample_bytree=best_params["colsample_bytree"],\
                             objective=best_params["objective"],\
                             nthread=best_params["nthread"],\
                             seed=best_params["seed"],\
                             num_class = self.N_Class)
    df_fmp = np.zeros((self.K, X.shape[1]))
    for fold_, (train_index, valid_index) in enumerate(self.skfold.split(X.values, y)):
      try:
        m_path = self.model_path + "000{}.model.pickle.dat".format(fold_)
        m = pickle.load(open(m_path, "rb"))
        m.save_model(self.model_path + "000{}.model".format(fold_))
        model = self.model_path + "000{}.model".format(fold_)
      except:
        model = None
      train_X, valid_X = X.values[train_index], X.values[valid_index]
      train_y, valid_y = y[train_index], y[valid_index]
      estimator = clf_best.fit(train_X, train_y, eval_set=[(valid_X, valid_y)], verbose=5, xgb_model=model, early_stopping_rounds=100)
      if save == True:
        pickle.dump(estimator, open(self.model_path+"000{}.model.pickle.dat".format(fold_), "wb"))
        if model != None:
          os.remove(self.model_path + "000{}.model".format(fold_))
      df_fmp[fold_] = estimator.feature_importances_
    if fmp == True:
      return df_fmp

  def featureSelect(self, fmp):
    df_fmp = pd.DataFrame(fmp, columns=self.preds+["byte_{}".format(i) for i in range(256)])
    fmp_mean = df_fmp.mean()
    THRESHOLD = 0
    preds_sel = fmp_mean[fmp_mean > THRESHOLD].index.tolist()
    with open(self.model_path+"preds_sel.txt", "w") as text_file:
      text_file.write(str(preds_sel))
    return preds_sel

if __name__ == "__main__":
  load_main = Main()
  parser = ArgumentParser()
  parser.add_argument("-f", help="filepath", dest="filepath")
  args = parser.parse_args()
  best_params = None
  preds_sel = None
  load_main.initialEnv()
  train = pd.read_csv(args.filepath)
  X, y = load_main.processData(train)
  if best_params == None:
    best_params = load_main.paraGridSearch(X, y)
  if preds_sel == None:
    fmp = load_main.model(best_params, X, y, fmp=True)
    preds_sel = load_main.featureSelect(fmp)
  X = X[preds_sel]
  load_main.model(best_params, X, y, save=True)
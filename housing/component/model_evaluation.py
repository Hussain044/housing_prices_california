from re import X
from tkinter import E
from housing.entity.artifact_entity import DataIngestionArtifact, DataValidationArtifact, ModelEvaluationArtifact, ModelTrainerArtifact
from housing.entity.config_entity import ModelEvaluationConfig
from housing.entity.model_factory import MetricInfoArtifact, evaluate_regression_model
from housing.exception import HousingException
from housing.logger import logging
import os
import sys
from housing.constant import *
from housing.util.util import *


class ModelEvaluation:
    def __init__(self, model_evaluation_config: ModelEvaluationConfig,
                 model_trainer_artifact: ModelTrainerArtifact,
                 data_ingestion_artifact: DataIngestionArtifact,
                 data_validation_artifact: DataValidationArtifact):
        try:
            logging.info(f"{'>>'*30}Model Evaluation log started.{'<<'*30}")
            self.model_evaluation_config = model_evaluation_config
            self.model_trainer_artifact = model_trainer_artifact
            self.data_ingestion_artifact = data_ingestion_artifact
            self.data_validation_artifact = data_validation_artifact

        except Exception as e:
            raise HousingException(e, sys) from e

    def get_best_model(self):
        try:
            model = None
            model_evaluation_file_path = self.model_evaluation_config.evaluated_model_file_path

            if not os.path.exists(model_evaluation_file_path):
                write_yaml_file(model_evaluation_file_path)
                return model

            model_eval_file_content = read_yaml_file(
                model_evaluation_file_path)

            model_eval_file_content = dict(
            ) if model_eval_file_content is None else model_eval_file_content

            if BEST_MODEL_KEY not in model_eval_file_content:
                return model

            model = load_object(
                file_path=model_eval_file_content[BEST_MODEL_KEY][MODEL_PATH_KEY])
            return model

        except Exception as e:
            raise HousingException(e, sys) from e

    def update_evaluation_model(self, model_evaluation_artifact):
        try:
            model_eval_file_path = self.model_evaluation_config.evaluated_model_file_path
            model_eval_file_content = read_yaml_file(model_eval_file_path)
            model_eval_file_content = dict(
            ) if model_eval_file_content is None else model_eval_file_content

            previous_best_model = None
            if BEST_MODEL_KEY in model_eval_file_content:
                previous_best_model = model_eval_file_content[BEST_MODEL_KEY]
            logging.info(f"previous model: {previous_best_model}")

            eval_result = {
                BEST_MODEL_KEY: {
                    MODEL_PATH_KEY: model_evaluation_artifact.evaluated_model_path,
                }
            }
            if previous_best_model is not None:
                model_history = {
                    self.model_evaluation_config.time_stamp: previous_best_model}
                if HISTORY_KEY not in model_eval_file_content:
                    history = {HISTORY_KEY: model_history}
                    eval_result.update(history)
                else:
                    model_eval_file_content[HISTORY_KEY].update(model_history)

            model_eval_file_content.update(eval_result)
            logging.info(f"Updated eval result:{model_eval_file_content}")
            write_yaml_file(file_path=model_eval_file_path,
                            data=model_eval_file_content)
        except Exception as e:
            raise HousingException(e, sys) from e

    def initiate_model_evaluation(self):
        try:
            trained_model_file_path = self.model_trainer_artifact.trained_model_file_path
            trained_model_object = load_object(
                file_path=trained_model_file_path)

            train_file_path = self.data_ingestion_artifact.train_file_path
            test_file_path = self.data_ingestion_artifact.test_file_path

            schema_file_path = self.data_validation_artifact.schema_file_path

            train_dataframe = load_data(
                file_path=train_file_path, schema_file_path=schema_file_path)
            test_dataframe = load_data(
                file_path=test_file_path, schema_file_path=schema_file_path)

            schema_content = read_yaml_file(schema_file_path)

            target_column_name = schema_content[TARGET_COLUMN_KEY]

            logging.info("Converting target column to numpy array")

            train_target_arr = np.array(train_dataframe[target_column_name])
            test_target_arr = np.array(test_dataframe[target_column_name])

            logging.info("Dropping target column from the dataframe")

            train_dataframe.drop(target_column_name, axis=1, inplace=True)
            test_dataframe.drop(target_column_name, axis=1, inplace=True)

            model = self.get_best_model()

            if model is None:
                logging.info(
                    "Not found any existing model, hence accepting trained model")
                model_evaluation_artifact = ModelEvaluationArtifact(is_model_accepted=True,
                                                                    evaluated_model_path=trained_model_file_path)
                self.update_evaluation_model(model_evaluation_artifact)

                return model_evaluation_artifact

            model_list = [model, trained_model_object]

            metric_info_artifact = evaluate_regression_model(model_list=model_list,
                                                             X_train=train_dataframe,
                                                             y_train=train_target_arr,
                                                             X_test=test_dataframe,
                                                             y_test=test_target_arr,
                                                             base_accuracy=self.model_trainer_artifact.model_accuracy)

            if metric_info_artifact is None:
                response = ModelEvaluationArtifact(is_model_accepted=False,
                                                   evaluated_model_path=trained_model_file_path)
                logging.info(f"{response}")
                return response

            if metric_info_artifact.index_number == 1:
                model_evaluation_artifact = ModelEvaluationArtifact(is_model_accepted=True,
                                                                    evaluated_model_path=trained_model_file_path)
                self.update_evaluation_model(model_evaluation_artifact)
                logging.info(
                    f"Model accepted. Model eval artifact {model_evaluation_artifact} created")

            else:
                logging.info(
                    "Trained model is no better than existing model hence not accepting trained model")
                model_evaluation_artifact = ModelEvaluationArtifact(evaluated_model_path=trained_model_file_path,
                                                                    is_model_accepted=False)
            return model_evaluation_artifact

        except Exception as e:
            raise HousingException(e, sys) from e

    def __del__(self):
        logging.info(f"{'>>'*30}Model Evaluation log ended.{'<<'*30}")

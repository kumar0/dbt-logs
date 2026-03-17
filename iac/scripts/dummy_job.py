"""
Minimal PySpark dummy Glue job for testing the Glue monitoring dashboard.
Accepts --entity_name and --run_date arguments, sleeps briefly, and exits.
"""

import sys
import time

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext

args = getResolvedOptions(sys.argv, ["JOB_NAME", "entity_name", "run_date"])

sc = SparkContext()
glue_context = GlueContext(sc)
logger = glue_context.get_logger()
job = Job(glue_context)
job.init(args["JOB_NAME"], args)

logger.info(
    f"Dummy Glue job started — entity_name={args['entity_name']}, run_date={args['run_date']}"
)

time.sleep(10)

logger.info("Dummy Glue job completed successfully")
job.commit()

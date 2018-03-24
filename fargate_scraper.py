import argparse
import boto3
import json
import logging
import signal
import sys

from collections import defaultdict
from threading import Event
from typing import Iterator, List

__version__ = "0.0.2"

LOGGER = logging.getLogger("fargate_scraper")
LOGFMT = "[%(asctime)s] [PID %(process)d] [%(threadName)s] [%(name)s] [%(levelname)s] %(message)s"
REQUIRED_ENV_VARS = ["METRICS_PORT"]


def parse_args():
    parser = argparse.ArgumentParser(description="Find the private IP addresses and ports of all scrape-able services running in an ECS cluster.")  # noqa
    parser.add_argument("--cluster-name", "-C", required=True, help="The name of the ECS cluster to search.")
    parser.add_argument("--interval", default=15, type=int, help="The interval (in seconds) at which to scrape Tasks.")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("filename", help="The name of the file to write results to.")
    return parser.parse_args()


def make_paginator(items_key):
    def paginator(fn, *args, **kwargs):
        token = ""
        while True:
            response = fn(*args, **{
                "nextToken": token,
                **kwargs,
            })

            items = response.get(items_key, [])
            token = response.get("nextToken")
            for item in items:
                yield item

            if not token:
                break

    return paginator


def chunk(iterable, chunksize=10):
    chunk = []
    for item in iterable:
        chunk.append(item)

        if len(chunk) == chunksize:
            yield chunk
            chunk[:] = []

    if chunk:
        yield chunk


class Scraper:
    def __init__(self, cluster: str, filename: str, interval: int = 15) -> None:
        self.ecs = boto3.client("ecs")
        self.cluster = cluster
        self.filename = filename
        self.interval = interval
        self.shutdown_event = Event()

    def start(self) -> None:
        LOGGER.info("Starting scraper...")
        self.running = True
        while self.running:
            try:
                LOGGER.debug("Looking up configs...")
                configs = self.get_configs()

                LOGGER.debug("Dumping configs...")
                with open(self.filename, "w") as f:
                    json.dump(configs, f, indent=4)
            except Exception:
                LOGGER.exception("Unhandled error encountered.")
            finally:
                LOGGER.debug("Sleeping for %d seconds...", self.interval)
                self.shutdown_event.wait(timeout=self.interval)

        LOGGER.info("Scraper stopped.")

    def stop(self) -> None:
        LOGGER.info("Stopping scraper...")
        self.running = False
        self.shutdown_event.set()

    def get_all_task_definitions(self) -> Iterator[str]:
        service_arns = make_paginator("serviceArns")(
            self.ecs.list_services,
            cluster=self.cluster,
            launchType="FARGATE",
        )

        for subset in chunk(service_arns):
            descriptions = self.ecs.describe_services(
                cluster=self.cluster,
                services=subset,
            ).get("services", [])

            for description in descriptions:
                if description["status"] == "ACTIVE":
                    yield description["taskDefinition"]

    def get_scrapable_task_definitions(self) -> List[dict]:
        scrapable_task_definitions = {}
        for task_definition in self.get_all_task_definitions():
            definition = self.ecs.describe_task_definition(taskDefinition=task_definition).get("taskDefinition", {})
            container_definitions = definition.get("containerDefinitions", [])
            for container_definition in container_definitions:
                environment = container_definition.get("environment", [])
                for env_var in environment:
                    name, value = env_var["name"], env_var["value"]
                    if name in REQUIRED_ENV_VARS:
                        scrapable_task_definitions.setdefault(task_definition, {})
                        scrapable_task_definitions[task_definition][name] = value
                        scrapable_task_definitions[task_definition]["FAMILY"] = definition["family"]

        return scrapable_task_definitions

    def get_configs(self) -> Iterator[str]:
        task_arns = make_paginator("taskArns")(
            self.ecs.list_tasks,
            cluster=self.cluster,
            desiredStatus="RUNNING",
            launchType="FARGATE",
        )

        scrapable_configs = defaultdict(list)
        scrapable_task_definitions = self.get_scrapable_task_definitions()
        for subset in chunk(task_arns, chunksize=100):
            descriptions = self.ecs.describe_tasks(
                cluster=self.cluster,
                tasks=subset,
            ).get("tasks", [])

            for description in descriptions:
                task_definition_arn = description.get("taskDefinitionArn")
                task_definition_vars = scrapable_task_definitions.get(task_definition_arn)
                if not task_definition_vars:
                    continue

                attachments = description.get("attachments", [])
                for attachment in attachments:
                    attachment_type = attachment.get("type")
                    attachment_status = attachment.get("status")
                    if not (attachment_type == "ElasticNetworkInterface" and attachment_status == "ATTACHED"):
                        continue

                    attachment_details = attachment.get("details", [])
                    for details in attachment_details:
                        name, value = details["name"], details["value"]
                        if name == "privateIPv4Address":
                            port = task_definition_vars.get("METRICS_PORT", 8000)
                            family = task_definition_vars.get("FAMILY", "unknown")
                            scrapable_configs[family].append("%(host)s:%(port)s" % {
                                "host": value,
                                "port": port,
                            })

        return [{
            "targets": targets,
            "labels": {
                "family": family,
            }
        } for family, targets in scrapable_configs.items()]


def main():
    logging.basicConfig(level=logging.DEBUG, format=LOGFMT)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    args = parse_args()
    scraper = Scraper(
        args.cluster_name,
        args.filename,
        args.interval,
    )

    def shutdown(signum, frame):
        scraper.stop()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    scraper.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())

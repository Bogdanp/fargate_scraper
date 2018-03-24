# Fargate Scraper

A CLI tool that scrapes [Fargate] tasks to find [Prometheus] targets.

[Fargate]: https://aws.amazon.com/fargate/
[Prometheus]: https://prometheus.io/


## Installation

    pip install fargate-scraper


## Usage

Give the script the name of the ECS cluster you want to scrape and the
location of where it should output the results.  It will automatically
pick up credentials from its environment.  See [boto3] for details.

```
fargate-scraper --cluster-name my-cluster output.json
```

Then point your prometheus config at that file.

``` yaml
scrape_configs:
  - job_name: prometheus
    metrics_path: "/metrics"
    file_sd_configs:
      - files:
          - output.json
        refresh_interval: 10m
```

Prometheus will automatically pick up changes to the file.

The script will pick up any Fargate containers that have a
`METRIC_PORT` env var defined.

[boto3]: https://boto3.readthedocs.io/en/latest/


## License

fargate_scraper is licensed under Apache 2.0.  Please see [LICENSE]
for licensing details.

[LICENSE]: https://github.com/Bogdanp/fargate_scraper/blob/master/LICENSE

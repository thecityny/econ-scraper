import "dotenv/config";

import core from "@actions/core";
import fs from "fs";
import {utcDay, utcSaturday} from "d3-time";
import {sum, rollup, mean} from "d3-array";

import axios from "axios";
import axiosRetry from "axios-retry";
import parseLinkHeader from "parse-link-header";

import {HttpRequest} from "@aws-sdk/protocol-http";
import {SignatureV4} from "@aws-sdk/signature-v4";
import AWSCrypto from '@aws-crypto/sha256-js';
const {Sha256} = AWSCrypto;

const apiClient = getAuthenticatedClient("https://jqhw3hn5d8.execute-api.us-east-1.amazonaws.com/", {
  region: process.env.AWS_REGION,
  accessKeyId: process.env.AWS_ACCESS_KEY_ID, 
  secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY
});

async function main() {
  try {
    await Promise.all([
      downloadDailyEntries("data/daily-entries.json", "daily entries"),
      downloadComplexEntries("data/complex-entries.json", "complex entries")
    ]);

    // Calculate weekly average for 2019
    // const avg = await getIntervalAverage(2019, utcSaturday);
    // console.log(avg);

  } catch (error) {
    core.setFailed(error);
  }
}

// Download daily total entries
async function downloadDailyEntries(path, label) {
  const data = await getEntries(Date.UTC(2019, 0, 1, 0, 0, 0, 0));

  console.log(`Saving ${label} to ${path}`);
  fs.writeFileSync(path, JSON.stringify(data, null, 2));
}

// Download entries for the current week, previous week and 2019 average for each complex
async function downloadComplexEntries(path, label) {
  // Get the latest available date from the API
  const latestRequest = await apiClient("/daily-complex-entries?per_page=1");
  const latestDate = new Date(parseISODateString(latestRequest.data[0].date));

  // Read or download 2019 average weekly complex entries
  const complexAveragesFile = await getDataFromPath("data/average-weekly-complex-entries-2019.json", async () => {
    const averages = await getComplexIntervalAverage(2019, utcSaturday);
    const data = Object.fromEntries(averages.entries());
    return JSON.stringify(data, null, 2);
  });
  const complexAverages = JSON.parse(complexAveragesFile);

  // Interval end is exclusive, so increment latestDate by one day
  const endDate = utcDay.offset(latestDate, 1);
  const weekTotals = await getComplexIntervalTotals(endDate, utcSaturday, 1);

  // Join current and baseline data
  const totals = [...weekTotals].map(([id, complex]) => {
    const currentWeek = complex[0];
    const average = complexAverages[id];

    return {
      id,
      week: currentWeek && getISODateString(currentWeek[0]),
      currentWeek: currentWeek && currentWeek[1],
      baseline: Math.round(average)
    };
  });

  console.log(`Saving ${label} to ${path}`);
  fs.writeFileSync(path, JSON.stringify(totals, null, 2));
}

// Get data at the given path, or write it if it doesn't exist
async function getDataFromPath(path, dataFunction = () => {}) {
  if (fs.existsSync(path)) {
    const data = fs.readFileSync(path);
    return data;
  }

  const data = await dataFunction();
  console.log(`Writing to ${path}`);
  fs.writeFileSync(path, data);
  return data;
}

// Get average entries per interval for a given year
async function getIntervalAverage(year, interval, step = 1) {
  const dateRange = getDateRangeForYear(year, interval, step);
  const [since, until] = getBoundsFromDateRange(dateRange);

  // Get the data
  const data = await getEntries(since, until);
  const grouped = groupByDateRange(dateRange.slice(0, -1), data, d => parseISODateString(d.date));
  // Return array of summed entries for each range in reverse chron order
  const sums = grouped.map(([date, d]) => sum(d, d => d.entries));
  return mean(sums);
}

// Get average complex interval per interval for a given year, return as map of averages
async function getComplexIntervalAverage(year, interval, step = 1) {
  const dateRange = getDateRangeForYear(year, interval, step);
  const [since, until] = getBoundsFromDateRange(dateRange);

  // Get the data
  const data = await getComplexEntries(since, until);
  return rollup(data, v => {
    // Group array of counts for the same complex by given date range
    const grouped = groupByDateRange(dateRange, v, d => parseISODateString(d.date));
    // Return array of summed entries for each range in reverse chron order
    const sums = grouped.map(([date, d]) => sum(d, d => d.entries));
    return mean(sums);
  }, d => d.complex_id);
}

// Generate date ranges in a given year. Final boundary may cross into next year.
function getDateRangeForYear(year, interval, step = 1) {
  const start = new Date(Date.UTC(year, 0, 1, 0, 0, 0, 0));
  const end = new Date(Date.UTC(year, 11, 31, 0, 0, 0, 0));
  const dateRange = interval.range(start, end, step);

  // Offset from last boundary to include ranges crossing year boundary
  const lastBoundary = dateRange[dateRange.length - 1];
  const endOfInterval = interval.offset(lastBoundary, step);
  return [...dateRange, endOfInterval];
}

// Get total complex entries per interval for given number of intervals from the end date, return as map of entries
async function getComplexIntervalTotals(end, interval, count = 1, step = 1) {
  const dateRange = getDateRangeFromEnd(end, interval, count, step);
  const [since, until] = getBoundsFromDateRange(dateRange);

  // Get the data
  const data = await getComplexEntries(since, until);
  return rollup(data, v => {
    // Group array of counts for the same complex by given date range
    const grouped = groupByDateRange(dateRange, v, d => parseISODateString(d.date));
    // Return array of summed entries for each range in reverse chron order
    return grouped.map(([date, d]) => [date, sum(d, d => d.entries)]).reverse();
  }, d => d.complex_id);
}

// Generate date ranges relative to end date. Final boundary will not exceed end date.
function getDateRangeFromEnd(endDate, interval, count = 1, step = 1) {
  // Increase count and day by one to account for max boundary
  const end = utcDay.offset(endDate, 1);
  const offset = step * (count + 1);
  const start = interval.offset(end, -Math.abs(offset));
  return interval.range(start, end, step);
}

// Given date range with exclusive final value, return inclusive bounds
function getBoundsFromDateRange(dateRange) {
  const lastBoundary = dateRange[dateRange.length - 1];
  // API is inclusive, so offset "until" by -1 day
  const until = utcDay.offset(lastBoundary, -1);
  const since = dateRange[0];

  return [since, until];
}

// Group the data based on the generated boundaries
function groupByDateRange(dateRange, data = [], dateAccessor = d => d) {
  const grouped = data.reduce((grouped, d) => {
    const parsedDate = dateAccessor(d);

    // Iterate through the boundaries until the date matches
    for (let i = 0; i < dateRange.length - 1; i += 1) {
      const start = dateRange[i].getTime();
      const end = dateRange[i + 1] && dateRange[i + 1].getTime() || Infinity;

      // If the date matches, add to the total
      if (parsedDate >= start && parsedDate < end) {
        const values = grouped.get(dateRange[i]) || [];
        grouped.set(dateRange[i], [...values, d]);
        return grouped;
      }
    }

    return grouped;
  }, new Map());

  return dateRange.slice(0, -1).map(date => [date, grouped.get(date) || []]);
}

// Query daily entries from turnstile API
async function getEntries(sinceDate, untilDate) {
  const since = getISODateString(sinceDate);
  const until = getISODateString(untilDate);
  return getPaginatedEntries(apiClient, `/daily-entries?since=${since || ""}&until=${until || ""}&per_page=5000`);
}

// Query complex entries from turnstile API
async function getComplexEntries(sinceDate, untilDate) {
  const since = getISODateString(sinceDate);
  const until = getISODateString(untilDate);
  return getPaginatedEntries(apiClient, `/daily-complex-entries?since=${since || ""}&until=${until || ""}&per_page=5000`);
}

// Convert date value to "YYYY-MM-DD"
function getISODateString(maybeDate) {
  const date = new Date(maybeDate);

  if (!isNaN(date)) {
    return date.toISOString().split("T")[0];
  }
}

// Return UTC timestamp given ISO date string ("YYYY-MM-DD")
function parseISODateString(isoString) {
  const dateParts = isoString.split("-").map(d => Number(d));
  return Date.UTC(dateParts[0], dateParts[1] - 1, dateParts[2], 0, 0, 0, 0);
}

// Recursively get all data from paginated API
async function getPaginatedEntries(client, url, data = []) {
  console.log(`Downloading ${url}`);

  const response = await client(url);
  const newData = [].concat(data, response.data);
  const links = parseLinkHeader(response.headers.link);

  // If there's a "next" link header, get the data at the URL
  if (links && links.next) {
    return getPaginatedEntries(client, links.next.url, newData);
  }

  return newData;
}

// Return function that accepts a relative URL and returns an authenticated
// Axios GET request 
function getAuthenticatedClient(base, {region, accessKeyId, secretAccessKey}) {
  const client = axios.create();
  
  // Configure retry, since scaling up the Aurora Serverless database can cause 
  // first request to time out.
  axiosRetry(client, {
    retries: 2,
    retryDelay: (retryCount) => {
      console.log(`Retry attempt: ${retryCount}`);
      return retryCount * 2000;
    },
    retryCondition: (error) => {
      return error.response.status === 503;
    }
  });

  return async (path) => {
    const url = new URL(path, base);

    // Construct HttpRequest for signer
    const request = new HttpRequest({
      headers: {
        host: url.host
      },
      hostname: url.hostname,
      method: "GET",
      path: url.pathname,
      query: Object.fromEntries(url.searchParams)
    });

    // Sign request with the given credentials
    const signer = new SignatureV4({
      region,
      credentials: {
        accessKeyId, 
        secretAccessKey
      },
      service: "execute-api",
      sha256: Sha256,
    });
    const signedRequest = await signer.sign(request);

    // Use the signed headers to build an Axios request
    return client({
      method: "get",
      url: url.href,
      headers: signedRequest.headers
    });
  };
}

main();

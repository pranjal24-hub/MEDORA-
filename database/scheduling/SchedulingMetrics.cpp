#include <iostream>
#include <stdexcept>
#include "SchedulingMetrics.h"

using namespace std;

SchedulingMetrics calculateMetrics(
    const vector<EmergencyRequest>& requests,
    const vector<int>& turnaroundTimes,
    int completedRequests,
    int cancelledRequests)
{
    if (requests.size() != turnaroundTimes.size())
    {
        throw invalid_argument(
            "Each request must have a turnaround time.");
    }

    if (completedRequests < 0 || cancelledRequests < 0)
    {
        throw invalid_argument(
            "Request counts cannot be negative.");
    }

    double totalWaitingTime = 0;
    double totalTurnaroundTime = 0;

    for (size_t i = 0; i < requests.size(); i++)
    {
        totalWaitingTime += requests[i].waitingTime;
        totalTurnaroundTime += turnaroundTimes[i];
    }

    SchedulingMetrics metrics;

    if (requests.empty())
    {
        metrics.averageWaitingTime = 0;
        metrics.averageTurnaroundTime = 0;
    }
    else
    {
        metrics.averageWaitingTime =
            totalWaitingTime / requests.size();

        metrics.averageTurnaroundTime =
            totalTurnaroundTime / turnaroundTimes.size();
    }

    metrics.completedRequests = completedRequests;
    metrics.cancelledRequests = cancelledRequests;

    return metrics;
}

void displayMetrics(const SchedulingMetrics& metrics)
{
    cout << "\n--- MEDORA Scheduling Metrics ---" << endl;

    cout << "Average Waiting Time: "
         << metrics.averageWaitingTime << " minutes" << endl;

    cout << "Average Turnaround Time: "
         << metrics.averageTurnaroundTime << " minutes" << endl;

    cout << "Completed Requests: "
         << metrics.completedRequests << endl;

    cout << "Cancelled Requests: "
         << metrics.cancelledRequests << endl;
}
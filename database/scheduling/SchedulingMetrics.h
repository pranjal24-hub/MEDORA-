#ifndef SCHEDULING_METRICS_H
#define SCHEDULING_METRICS_H

#include <vector>
#include "EmergencyRequest.h"

struct SchedulingMetrics
{
    double averageWaitingTime;
    double averageTurnaroundTime;
    int completedRequests;
    int cancelledRequests;
};

SchedulingMetrics calculateMetrics(
    const std::vector<EmergencyRequest>& requests,
    const std::vector<int>& turnaroundTimes,
    int completedRequests,
    int cancelledRequests
);

void displayMetrics(const SchedulingMetrics& metrics);

#endif
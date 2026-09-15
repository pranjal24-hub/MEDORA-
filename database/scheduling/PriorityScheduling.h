#ifndef PRIORITY_SCHEDULING_H
#define PRIORITY_SCHEDULING_H

#include <vector>
#include "EmergencyRequest.h"

using namespace std;

void prioritySchedule(vector<EmergencyRequest>& requests);

void displaySchedule(const vector<EmergencyRequest>& requests);

#endif
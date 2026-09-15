#ifndef EMERGENCY_REQUEST_H
#define EMERGENCY_REQUEST_H

#include <string>
#include <vector>

using namespace std;

struct EmergencyRequest
{
    int requestId;
    string ambulanceId;
    string patientName;
    int severity;
    string requiredResource;
    int waitingTime;
};

void inputEmergencyRequests(vector<EmergencyRequest>& requests);

void displayEmergencyRequests(const vector<EmergencyRequest>& requests);

#endif
#include <iostream>
#include "EmergencyRequest.h"

using namespace std;

void inputEmergencyRequests(vector<EmergencyRequest>& requests)
{
    int n;

    cout << "MEDORA - Emergency Request Module" << endl;
    cout << "Enter number of emergency requests: ";
    cin >> n;

    for (int i = 0; i < n; i++)
    {
        EmergencyRequest request;

        request.requestId = i + 1;

        cout << "\nEnter details for request " << i + 1 << endl;

        cout << "Ambulance ID: ";
        cin >> request.ambulanceId;

        cout << "Patient Name: ";
        cin >> request.patientName;

        cout << "Severity (1-5): ";
        cin >> request.severity;

        cout << "Required Resource: ";
        cin >> request.requiredResource;

        cout << "Waiting Time (minutes): ";
        cin >> request.waitingTime;

        requests.push_back(request);
    }
}

void displayEmergencyRequests(const vector<EmergencyRequest>& requests)
{
    cout << "\n--- Emergency Requests ---" << endl;

    for (const auto& request : requests)
    {
        cout << "\nRequest ID: " << request.requestId;
        cout << "\nAmbulance: " << request.ambulanceId;
        cout << "\nPatient: " << request.patientName;
        cout << "\nSeverity: " << request.severity;
        cout << "\nRequired Resource: " << request.requiredResource;
        cout << "\nWaiting Time: " << request.waitingTime
             << " minutes\n";
    }
}
#ifndef AGING_POLICY_H
#define AGING_POLICY_H

#include <vector>
#include "EmergencyRequest.h"

using namespace std;

int calculateEffectivePriority(
    const EmergencyRequest& request,
    int agingInterval = 5
);

void applyAgingPolicy(
    vector<EmergencyRequest>& requests,
    int agingInterval = 5
);

#endif